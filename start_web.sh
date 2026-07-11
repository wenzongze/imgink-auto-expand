#!/bin/sh
# img.ink 自动扩容 - Web 面板保活/开机自启脚本
# 功能：若 web_app.py 未运行则自动拉起（带 PYTHONPATH，使其子进程能找到 requests）
# 用法：由 crontab 每 5 分钟调用一次，实现开机自启 + 意外退出自愈
# 注意：QNAP 默认无 pgrep/pkill，使用 ps + grep 判断进程是否存在

PY="/share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/python3"
DIR="/share/CACHEDEV1_DATA/Web/gadget/auto_sign"
LOG="$DIR/web.log"

export PYTHONPATH="/share/homes/Mars/.local/lib/python3.12/site-packages"

# 用 [w]eb_app.py 技巧避免匹配到 grep 自身
if ! ps aux | grep "[w]eb_app.py" > /dev/null 2>&1; then
    cd "$DIR" || exit 1
    "$PY" "$DIR/web_app.py" >> "$LOG" 2>&1 &
fi
