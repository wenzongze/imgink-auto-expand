#!/usr/bin/env python3
"""img.ink 看门狗：独立于 sign_expand.py 检查当日是否成功扩容。

若 expand_state.json 的 date 不是今天（或文件缺失/异常），发邮件告警。
用途：消灭「脚本根本没被触发运行」导致的静默失败——
即便 sign_expand.py 的触发链全断，本看门狗仍能发现「今日未扩容」并告警。
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import send_notify

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "expand_state.json")
today = time.strftime("%Y-%m-%d")

ok = False
detail = ""
try:
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        date = d.get("date")
        done = d.get("done")
        ok = (date == today and done is True)
        detail = "expand_state.json: date=%s done=%s" % (date, done)
    else:
        detail = "expand_state.json 不存在（脚本从未成功运行）"
except Exception as e:
    detail = "读取 expand_state.json 异常: %s" % e

if not ok:
    send_notify(
        "【img.ink 看门狗】今日未扩容",
        "今日(%s)尚未记录成功扩容。\n%s\n请检查 cron 是否被剥离 / 登录态 / disabled.flag / 网络连通性。" % (today, detail),
    )
else:
    print("[watchdog] OK: 今日已扩容 (%s)" % today)
