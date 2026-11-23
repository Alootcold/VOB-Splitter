"""命令行入口。

    python -m vobsplit scan  VOB... [--json]
    python -m vobsplit split  VOB... -o OUTDIR [选项]
    python -m vobsplit verify OUTDIR --source VOB...

选项：
    --mode auto|duration|times|whole   切分方式，默认 auto（按 DVD 章节表）
    --times  "0,218,489.28"             mode=times 的切点（秒，支持 hh:mm:ss）
    --interval 600                      mode=duration 的间隔秒数
    --min-chapter 2.0                   短于该值的章视为噪声并合并
    --pts-drop 1.0                      判定 PTS 回落的阈值（秒）
    --format vob|mkv|both               输出形式；mkv/both 需要 ffmpeg
    --ffmpeg PATH                       指定 ffmpeg 可执行文件
    --no-verify                         跳过 SHA-256 校验（不推荐）
    --prefix chapter                    输出文件名前缀
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .chapters import ChapterSpec, detect_chapters, parse_time_list
from .ps import VobSource, build_index
from .runner import Handlers, run_split
from .splitter import verify_outputs


def _fmt_time(sec: Optional[float]) -> str:
    if sec is None:
        return "-"
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return "%d:%02d:%06.3f" % (h, m, s)


def _collect_files(paths: List[str], include_menu: bool = False) -> List[str]:
    """展开目录参数：给目录就把里面所有 .vob 按 DVD 顺序排好。

    DVD 会额外放一个 VTS_xx_0.VOB 作为盘上菜单（标题 0），它不属于正片内容，
    展开目录时默认跳过；用 --include-menu 可以带上。
    """
    out: List[str] = []
    for p in paths:
        if os.path.isdir(p):
            vobs = sorted(f for f in os.listdir(p) if f.lower().endswith(".vob"))
            vobs.sort(key=_vob_sort_key)
            if not include_menu:
                skipped = [v for v in vobs if _is_menu_vob(v)]
                vobs = [v for v in vobs if not _is_menu_vob(v)]
                if skipped:
                    print("跳过菜单 VOB: %s（用 --include-menu 可包含）"
                          % ", ".join(skipped))
            out.extend(os.path.join(p, v) for v in vobs)
        else:
            out.append(p)
    return out


def _is_menu_vob(name: str) -> bool:
    """VTS_01_0.VOB / VTS_03_0.VOB 是盘上菜单（标题 0）。"""
    base = os.path.splitext(name)[0]
    parts = base.split("_")
    if len(parts) < 3:
        return False
    try:
        return int(parts[-1]) == 0
    except ValueError:
        return False


def _vob_sort_key(name: str):
    """VTS_01_1.VOB < VTS_01_2.VOB < VTS_01_10.VOB（按数字排序）。"""
    base = os.path.splitext(name)[0]
    parts = base.split("_")
    try:
        return (parts[0], int(parts[-1]))
    except (ValueError, IndexError):
        return (base, 0)


def _build_spec(args) -> ChapterSpec:
    if args.mode == "duration":
        return ChapterSpec.duration(args.interval, min_chapter=args.min_chapter)
    if args.mode == "times":
        times = parse_time_list(args.times or "")
        return ChapterSpec.times(times, min_chapter=args.min_chapter)
    if args.mode == "whole":
        return ChapterSpec.whole()
    return ChapterSpec.auto(pts_drop=args.pts_drop, min_chapter=args.min_chapter)


def _scan(source: VobSource, spec: ChapterSpec, quiet: bool = False,
          progress=None):
    if not quiet:
        print("扫描: %s" % ", ".join(os.path.basename(p) for p in source.paths))
        print("总大小: %d 字节 (%.2f GiB)" % (source.total_size,
                                             source.total_size / 1073741824.0))
    raps, stats = build_index(source, progress=progress)
    chapters = detect_chapters(raps, source.total_size, spec)
    if not quiet:
        print("pack=%d  非法pack=%d  视频PES=%d  随机访问点=%d"
              % (stats["packs"], stats["invalid_packs"], stats["video_pes"],
                 stats["raps"]))
        print("检测到 %d 章\n" % len(chapters))
        print("  %-4s %-14s %-14s %-14s %12s %8s"
              % ("章", "起始", "结束", "时长", "字节", "GOP"))
        for ch in chapters:
            print("  %-4d %-14s %-14s %-14s %12d %8d"
                  % (ch.index + 1, _fmt_time(ch.start_pts), _fmt_time(ch.end_pts),
                     _fmt_time(ch.duration), ch.size, ch.rap_count))
    return raps, chapters, stats


def cmd_scan(args) -> int:
    files = _collect_files(args.inputs, getattr(args, "include_menu", False))
    if not files:
        print("没有找到 VOB 文件", file=sys.stderr)
        return 2
    source = VobSource(files)
    spec = _build_spec(args)
    raps, stats = _scan(source, spec, quiet=bool(args.json),
                        progress=lambda frac: _print_progress(
                            "正在扫描码流… %d%%" % int(100 * frac)))
    if args.json:
        print(json.dumps({
            "files": [os.path.basename(p) for p in files],
            "total_size": source.total_size,
            "stats": stats,
            "chapters": [{
                "index": c.index, "start_offset": c.start_offset,
                "end_offset": c.end_offset, "bytes": c.size,
                "start_pts": c.start_pts, "end_pts": c.end_pts,
                "duration": c.duration, "rap_count": c.rap_count,
            } for c in chapters],
        }, indent=2, ensure_ascii=False))
    return 0


def _print_progress(message: str) -> None:
    """进度写到 stderr —— stdout 保持干净，方便重定向/管道。

    读光盘很慢（几 MB/s），没有进度条用户会以为卡死了。
    """
    sys.stderr.write("\r  %s" % message)
    sys.stderr.flush()


def cmd_split(args) -> int:
    files = _collect_files(args.inputs, getattr(args, "include_menu", False))
    if not files:
        print("没有找到 VOB 文件", file=sys.stderr)
        return 2
    spec = _build_spec(args)

    def on_chapters(chapters):
        print()
        print("  %-4s %-14s %-14s %-14s %12s %8s"
              % ("章", "起始", "结束", "时长", "字节", "GOP"))
        for c in chapters:
            print("  %-4d %-14s %-14s %-14s %12d %8d"
                  % (c.index + 1, _fmt_time(c.start_pts), _fmt_time(c.end_pts),
                     _fmt_time(c.duration), c.size, c.rap_count))
        print()
        print("开始切分 -> %s" % args.output)

    handlers = Handlers(log=print, chapters=on_chapters,
                        progress=lambda value, message: _print_progress(message))
    result = run_split(files, spec, args.output, prefix=args.prefix,
                       output_format=args.format, ffmpeg=args.ffmpeg,
                       verify=not args.no_verify, manifest=not args.no_manifest,
                       handlers=handlers)

    print()
    sys.stderr.write("\n")
    sys.stderr.flush()
    print("输出目录: %s" % args.output)
    print("章节数  : %d" % len(result.files))
    print("源字节  : %d" % result.source_bytes)
    print("出字节  : %d" % result.output_bytes)
    print("源SHA256: %s" % result.source_sha256)
    print("出SHA256: %s" % result.output_sha256)
    print("无损校验: %s" % ("通过（逐字节一致）" if result.verified else "未通过"))
    if result.manifest_path:
        print("清单: %s" % result.manifest_path)
    return 0 if (result.verified or args.no_verify) else 1


def _output_names(out_dir: str) -> List[str]:
    """优先按 manifest 里记录的章节文件列表。

    否则会把上一次切分残留的 .vob 一起算进去，导致哈希对不上而误报「不一致」。
    """
    manifest = os.path.join(out_dir, "vobsplit-manifest.json")
    if os.path.isfile(manifest):
        try:
            with open(manifest, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            names = [c["file"] for c in data.get("chapters", []) if c.get("file")]
            if names:
                return names
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return sorted(f for f in os.listdir(out_dir) if f.lower().endswith(".vob"))


def cmd_verify(args) -> int:
    files = _collect_files(args.source, getattr(args, "include_menu", False))
    source = VobSource(files)
    out_dir = args.directory
    names = _output_names(out_dir)
    if not names:
        print("目录里没有 .vob 文件", file=sys.stderr)
        return 2
    digest, total = verify_outputs(out_dir, names)
    src = source.sha256()
    print("源流  %d 字节  SHA-256 = %s" % (source.total_size, src))
    print("输出  %d 字节  SHA-256 = %s" % (total, digest))
    ok = src == digest and total == source.total_size
    print("结果: %s" % ("逐字节完全一致 —— 100% 无损" if ok else "不一致"))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vobsplit",
        description="DVD VOB 无损分割工具：按章节把 VOB 切成多个文件，逐字节无损。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    p.add_argument("--version", action="version", version="vobsplit " + __version__)
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("inputs", nargs="+", help="VOB 文件或包含 VOB 的目录")
        sp.add_argument("--mode", choices=("auto", "duration", "times", "whole"),
                        default="auto",
                        help="切分方式：auto=按 DVD 章节（默认）/duration=等长/"
                             "times=指定时间点/whole=不切")
        sp.add_argument("--times", default="",
                        help="mode=times 的切点，如 '0,218,489.28' 或 '00:03:38'")
        sp.add_argument("--interval", type=float, default=600.0,
                        help="mode=duration 的间隔秒数，默认 600")
        sp.add_argument("--min-chapter", type=float, default=2.0,
                        help="短于该秒数的章视为噪声并合并，默认 2.0")
        sp.add_argument("--pts-drop", type=float, default=1.0,
                        help="判定 PTS 回落的阈值（秒），默认 1.0")

    sp = sub.add_parser("scan", help="扫描并列出检测到的章节")
    add_common(sp)
    sp.add_argument("--json", action="store_true", help="输出 JSON")
    sp.add_argument("--include-menu", action="store_true",
                    help="展开目录时把 VTS_xx_0.VOB 菜单文件也算进去")
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("split", help="按章节切分")
    add_common(sp)
    sp.add_argument("-o", "--output", required=True, help="输出目录")
    sp.add_argument("--prefix", default="chapter", help="输出文件名前缀，默认 chapter")
    sp.add_argument("--format", choices=("vob", "mkv", "both"), default="vob",
                    help="输出形式，默认 vob；mkv/both 需要 ffmpeg")
    sp.add_argument("--ffmpeg", default=None, help="指定 ffmpeg 可执行文件")
    sp.add_argument("--no-verify", action="store_true", help="跳过 SHA-256 校验")
    sp.add_argument("--no-manifest", action="store_true", help="不写 JSON 清单")
    sp.add_argument("-q", "--quiet", action="store_true", help="安静模式")
    sp.add_argument("--include-menu", action="store_true",
                    help="展开目录时把 VTS_xx_0.VOB 菜单文件也算进去")
    sp.set_defaults(func=cmd_split)

    sp = sub.add_parser("verify", help="校验已有切分结果")
    sp.add_argument("directory", help="切分结果所在目录")
    sp.add_argument("--source", nargs="+", required=True, help="原始 VOB 文件或目录")
    sp.set_defaults(func=cmd_verify)
    return p


def _configure_stdio() -> None:
    """统一输出编码。

    重定向到文件/管道时用 UTF-8（与 Dart 版一致）；挂在控制台时保留控制台代码页，
    但把不可编码的字符替换掉，避免直接崩掉。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
