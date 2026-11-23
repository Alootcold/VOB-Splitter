#!/bin/sh
# 启动脚本：保证从固定路径启动 bundle 里的可执行文件。
# bundle 里的可执行文件靠 $ORIGIN/lib 找引擎库，$ORIGIN = 可执行文件所在目录，
# 所以不能把 exe 单独拎出来跑。
exec /usr/lib/vobsplit/vobsplit_gui "$@"
