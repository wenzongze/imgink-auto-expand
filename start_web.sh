#!/bin/sh
# img.ink 调度器（由 selfheal 的 IMG_CRON 每 5 分钟调用，幂等、只增不删）
#
# 负责把 3 条 cron 固化进 /etc/config/crontab 并安装到 crond spool：
#   扩容   : 每日 08:00 触发，sign_expand.py 内部随机落在 09:00-21:00 时段
#   自检   : 每日 23:00 sign_expand.py --check（登录失败 / 未扩容发邮件）
#   看门狗 : 每日 23:30 独立检查 expand_state.json（未扩容发邮件）
#
# 重要：QNAP 的 crond 真正读取 /tmp/cron/crontabs/admin（/etc/config/crontab 的拷贝），
#       任何 crontab 改动都必须 crontab /etc/config/crontab 安装进 spool 才生效。
#
# 设计变更（2026-08-02）：旧版此脚本会删除自身并依赖「web_app.py 内部随机触发」，
# 但 web_app.py 从无内部调度，导致 img.ink 完全失去自动触发。现改为单一 crontab 信源。

PY="/share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/python3"
AS="/share/CACHEDEV1_DATA/Web/gadget/auto_sign"
CT="/etc/config/crontab"

EXPAND="0 8 * * * cd $AS && $PY sign_expand.py >> $AS/cron.log 2>&1"
CHECK="0 23 * * * cd $AS && $PY sign_expand.py --check >> $AS/check.log 2>&1"
WATCH="30 23 * * * cd $AS && $PY watchdog.py >> $AS/watchdog.log 2>&1"

changed=0
if ! grep -qF "auto_sign/cron.log" "$CT" 2>/dev/null; then
  echo "$EXPAND" >> "$CT"; changed=1
fi
if ! grep -qF "auto_sign/check.log" "$CT" 2>/dev/null; then
  echo "$CHECK" >> "$CT"; changed=1
fi
if ! grep -qF "watchdog.py" "$CT" 2>/dev/null; then
  echo "$WATCH" >> "$CT"; changed=1
fi

if [ "$changed" = "1" ]; then
  crontab "$CT" 2>/dev/null || cp "$CT" /tmp/cron/crontabs/admin 2>/dev/null
  echo "[$(date)] img.ink crontab ensured (changed=$changed)" >> "$AS/web_keepalive.log"
fi
