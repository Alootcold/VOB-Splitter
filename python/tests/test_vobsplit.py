"""vobsplit 单元测试（只用标准库 unittest）。

    cd python && python -m unittest discover -s tests -v
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import synth
from vobsplit.chapters import ChapterSpec, detect_chapters, parse_time_spec, parse_time_list
from vobsplit.ps import VobSource, build_index, decode_timestamp
from vobsplit.splitter import split, verify_outputs


class TestTimestamp(unittest.TestCase):
    def test_roundtrip(self):
        for value in (0, 1, 2700, 90000, 123456789, 0x1FFFFFFFF):
            raw = synth.encode_timestamp(value)
            decoded = decode_timestamp(raw)
            self.assertIsNotNone(decoded)
            self.assertAlmostEqual(decoded, value / 90000.0, places=6)

    def test_rejects_garbage(self):
        self.assertIsNone(decode_timestamp(b"\x00\x00\x00\x00\x00"))
        self.assertIsNone(decode_timestamp(b"\xff\xff\xff\xff\xff"))


class TestTimeParsing(unittest.TestCase):
    def test_formats(self):
        self.assertAlmostEqual(parse_time_spec("90"), 90.0)
        self.assertAlmostEqual(parse_time_spec("1:30"), 90.0)
        self.assertAlmostEqual(parse_time_spec("00:01:30"), 90.0)
        self.assertAlmostEqual(parse_time_spec("00:01:30.5"), 90.5)
        self.assertAlmostEqual(parse_time_spec("1h2m3s"), 3723.0)
        self.assertEqual(parse_time_list("0, 218, 00:08:09.28"),
                         [0.0, 218.0, 489.28])


class TestChapterDetection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vobsplit-test-")
        self.path = os.path.join(self.tmp, "VTS_01_1.VOB")
        synth.write_vob(self.path, [6.0, 4.0, 8.0])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _chapters(self):
        source = VobSource([self.path])
        raps, stats = build_index(source)
        return detect_chapters(raps, source.total_size, ChapterSpec.auto()), raps, stats

    def test_detects_three_chapters(self):
        chapters, raps, stats = self._chapters()
        self.assertEqual(len(chapters), 3)
        self.assertGreater(stats["raps"], 10)
        self.assertEqual(stats["invalid_packs"], 0)

    def test_chapter_boundaries_are_pack_aligned(self):
        chapters, _, _ = self._chapters()
        for ch in chapters:
            self.assertEqual(ch.start_offset % 2048, 0)
            self.assertEqual(ch.end_offset % 2048, 0)

    def test_chapters_cover_whole_stream(self):
        chapters, _, _ = self._chapters()
        self.assertEqual(chapters[0].start_offset, 0)
        self.assertEqual(chapters[-1].end_offset,
                         os.path.getsize(self.path))

    def test_build_index_reports_progress(self):
        """扫描期间必须回报进度 —— 读光盘很慢，没有进度用户会以为卡死。"""
        source = VobSource([self.path])
        seen = []
        build_index(source, progress=seen.append)
        self.assertTrue(seen, "build_index 没有回报任何进度")
        self.assertTrue(all(0.0 <= v <= 1.0 for v in seen))
        self.assertGreater(seen[-1], 0.0)

    def test_single_program_has_one_chapter(self):
        path = os.path.join(self.tmp, "single.vob")
        synth.write_vob(path, [10.0])
        source = VobSource([path])
        raps, _ = build_index(source)
        chapters = detect_chapters(raps, source.total_size, ChapterSpec.auto())
        self.assertEqual(len(chapters), 1)

    def test_short_chapter_is_merged(self):
        """太短的章视为噪声，并入上一章。"""
        path = os.path.join(self.tmp, "short.vob")
        synth.write_vob(path, [6.0, 1.0, 6.0])
        source = VobSource([path])
        raps, _ = build_index(source)
        chapters = detect_chapters(raps, source.total_size,
                                   ChapterSpec.auto(min_chapter=2.0))
        self.assertEqual(len(chapters), 2)

    def test_first_chapter_starts_at_zero(self):
        """真实 DVD 的第一个 pack 是导航包（不是随机访问点）。

        首章必须仍然从字节 0 开始 —— 否则开头那段会被丢掉，
        「各章拼接 == 源流」的哈希校验就通不过。
        """
        chapters, _, _ = self._chapters()
        self.assertEqual(chapters[0].start_offset, 0)
        self.assertEqual(chapters[0].end_offset % 2048, 0)

    def test_global_timeline_is_monotonic(self):
        chapters, _, _ = self._chapters()
        for i in range(1, len(chapters)):
            self.assertGreater(chapters[i].global_start, chapters[i - 1].global_start)
            self.assertGreater(chapters[i].global_end, chapters[i].global_start)


class TestSplit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vobsplit-test-")
        self.path = os.path.join(self.tmp, "VTS_01_1.VOB")
        synth.write_vob(self.path, [6.0, 4.0, 8.0])
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _split(self, spec=None):
        source = VobSource([self.path])
        raps, _ = build_index(source)
        chapters = detect_chapters(raps, source.total_size, spec or ChapterSpec.auto())
        return split(source, chapters, self.out)

    def test_split_is_byte_exact(self):
        result = self._split()
        self.assertTrue(result.verified)
        self.assertEqual(result.source_bytes, result.output_bytes)
        self.assertEqual(result.source_sha256, result.output_sha256)

    def test_concatenation_equals_source(self):
        self._split()
        joined = hashlib.sha256()
        with open(self.path, "rb") as fh:
            original = fh.read()
        pieces = b""
        for name in result_names(self.out):
            with open(os.path.join(self.out, name), "rb") as fh:
                pieces += fh.read()
        joined.update(pieces)
        self.assertEqual(joined.hexdigest(), hashlib.sha256(original).hexdigest())
        self.assertEqual(pieces, original)

    def test_each_output_starts_with_pack_header(self):
        self._split()
        for name in result_names(self.out):
            with open(os.path.join(self.out, name), "rb") as fh:
                head = fh.read(4)
            self.assertEqual(head, b"\x00\x00\x01\xba")

    def test_manifest_written(self):
        result = self._split()
        self.assertTrue(os.path.isfile(result.manifest_path))
        self.assertEqual(len(result.chapters), 3)

    def test_multi_file_source(self):
        """DVD 会把标题切成多个 VOB，必须当作一条连续流处理。"""
        multi = os.path.join(self.tmp, "multi")
        os.makedirs(multi, exist_ok=True)
        paths = synth.write_vob(os.path.join(multi, "VTS_02_1.VOB"),
                                [6.0, 4.0, 8.0], split_at=3)
        source = VobSource(paths)
        raps, _ = build_index(source)
        chapters = detect_chapters(raps, source.total_size, ChapterSpec.auto())
        out = os.path.join(self.tmp, "out2")
        result = split(source, chapters, out)
        self.assertTrue(result.verified)
        self.assertEqual(len(chapters), 3)

    def test_duration_mode(self):
        source = VobSource([self.path])
        raps, _ = build_index(source)
        spec = ChapterSpec.duration(2.0, min_chapter=0.0)
        chapters = detect_chapters(raps, source.total_size, spec)
        self.assertGreater(len(chapters), 1)

    def test_times_mode(self):
        source = VobSource([self.path])
        raps, _ = build_index(source)
        spec = ChapterSpec.times([2.0], min_chapter=0.0)
        chapters = detect_chapters(raps, source.total_size, spec)
        self.assertEqual(len(chapters), 2)


def result_names(out_dir):
    return sorted(f for f in os.listdir(out_dir) if f.endswith(".vob"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
