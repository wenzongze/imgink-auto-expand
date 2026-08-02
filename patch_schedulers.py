#!/usr/bin/env python3
# 一次性补丁：修复两套调度脚本对 img.ink 自动触发的破坏，并加入看门狗 cron。
# 由 nas_push.ps1 的 -AfterCmd 在 NAS 上以 root 运行，运行后即删。

def patch_dashboard(path):
    s = open(path, encoding="utf-8").read()
    start = s.index("# ---------- 5) 清理旧 auto_sign 冗余脚本 ----------")
    end = s.index("# ---------- 6) 配置 admin(=root) 免密登录")
    new_block = '''# ---------- 5) 确保 img.ink 调度器存活（不再删除 auto_sign） ----------
# 旧逻辑会 rm -f auto_sign/start_web.sh 与 web_app.py，导致 img.ink 失去自动调度。
# 现改为：确保 auto_sign/start_web.sh 的 */5 保活 cron 存在，并立即以 root 上下文
# 运行它来安装 扩容 / 自检 / 看门狗 三条 cron（绝不删除任何 auto_sign 文件）。
_AS_SW="/share/CACHEDEV1_DATA/Web/gadget/auto_sign/start_web.sh"
_IMG_CRON="*/5 * * * * /bin/sh $_AS_SW >> /share/CACHEDEV1_DATA/Web/gadget/auto_sign/web_keepalive.log 2>&1"
if [ "$(id -u)" = "0" ]; then
    if ! grep -qF "auto_sign/start_web.sh" "$CT" 2>/dev/null; then
        _T="/tmp/asimg.$$"
        grep -vF "auto_sign/start_web.sh" "$CT" > "$_T" 2>/dev/null
        echo "$_IMG_CRON" >> "$_T"
        if cat "$_T" > "$CT" 2>/dev/null; then
            install_crontab
            echo "[$(date)] ensured auto_sign/start_web.sh cron entry" >> "$LOG"
        fi
        rm -f "$_T"
    fi
    # 立即装上 3 条 img.ink cron（root 可写 /etc/config/crontab）
    /bin/sh "$_AS_SW"
fi
'''
    s = s[:start] + new_block + "\n" + s[end:]
    open(path, "w", encoding="utf-8").write(s)
    print("patched dashboard/start_web.sh")


def patch_selfheal(path):
    s = open(path, encoding="utf-8").read()
    old1 = 'IMG_CRON="*/5 * * * * /bin/sh $IMG_DIR/start_web.sh >> $IMG_DIR/web_keepalive.log 2>&1"\n'
    assert old1 in s, "selfheal IMG_CRON def not found"
    new1 = old1 + (
        'EXPAND_CRON="0 8 * * * cd $IMG_DIR && /share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/python3 $IMG_DIR/sign_expand.py >> $IMG_DIR/cron.log 2>&1"\n'
        'WATCHDOG_CRON="30 23 * * * cd $IMG_DIR && /share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/python3 $IMG_DIR/watchdog.py >> $IMG_DIR/watchdog.log 2>&1"\n'
    )
    s = s.replace(old1, new1, 1)

    old2 = 'echo "$CHECK_CRON" >> "$TMP_CRON"\n'
    assert old2 in s, "selfheal CHECK_CRON echo not found"
    new2 = old2 + (
        'echo "$EXPAND_CRON" >> "$TMP_CRON"\n'
        'echo "$WATCHDOG_CRON" >> "$TMP_CRON"\n'
    )
    s = s.replace(old2, new2, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("patched microsoft/nas_selfheal.sh")


patch_dashboard("/share/CACHEDEV1_DATA/Web/gadget/dashboard/start_web.sh")
patch_selfheal("/share/CACHEDEV1_DATA/Web/gadget/microsoft/nas_selfheal.sh")
print("ALL PATCHES DONE")
