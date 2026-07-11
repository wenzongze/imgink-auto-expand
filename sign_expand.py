#!/usr/bin/env python3
"""img.ink 每日自动扩容签到脚本"""
import random
import time
import re
import configparser
import os
import sys

import requests
from notify import send_notify

# --- 读取配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cfg = configparser.ConfigParser()
cfg.read(os.path.join(BASE_DIR, "config.ini"), encoding="utf-8")

ACCOUNT  = cfg["ACCOUNT"]["account"]
PASSWORD = cfg["ACCOUNT"]["password"]
LOGIN_URL  = cfg["SETTING"]["login_url"]
EXPAND_URL = cfg["SETTING"]["expand_url"]
RANDOM_START = int(cfg["SETTING"]["random_start"])
RANDOM_END   = int(cfg["SETTING"]["random_end"])
DISABLED_FLAG = os.path.join(BASE_DIR, "disabled.flag")

# 判断是否为手动触发：优先读环境变量 MANUAL（由 Web 面板设置），
# 兼容命令行 --manual / -m 参数，避免参数传递异常导致误入随机等待
MANUAL_MODE = os.environ.get("MANUAL") == "1" or "--manual" in sys.argv or "-m" in sys.argv


def check_disabled():
    """检查是否已暂停（通过 Web 面板控制）"""
    if os.path.exists(DISABLED_FLAG):
        print("[跳过] 计划任务已被 Web 面板暂停，如需恢复请在面板中启用")
        sys.exit(0)


def random_wait():
    """在指定时段内随机延迟，模仿真人操作时间"""
    now = time.localtime()
    current_minutes = now.tm_hour * 60 + now.tm_min
    start_minutes = RANDOM_START * 60
    end_minutes = RANDOM_END * 60

    if current_minutes < start_minutes:
        # 还没到开始时间，延迟到随机时间点
        delay = random.randint(start_minutes - current_minutes, end_minutes - current_minutes)
    elif current_minutes > end_minutes:
        # 已过结束时间，今天不再执行（Windows 计划任务会次日再触发）
        print(f"[跳过] 当前时间 {now.tm_hour:02d}:{now.tm_min:02d}，已超过设定时段 {RANDOM_START}:00-{RANDOM_END}:00")
        sys.exit(0)
    else:
        # 在当前时段内，随机延迟 1~30 分钟
        delay = random.randint(60, 1800)

    print(f"[等待] 随机延迟 {delay} 秒（约 {delay//60} 分钟）后执行...")
    time.sleep(delay)


def new_session():
    """创建带常见浏览器头的 Session"""
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return s


def get_token(session):
    """GET 登录页，提取 CSRF __token__"""
    resp = session.get(LOGIN_URL, timeout=(10, 15))
    resp.raise_for_status()
    match = re.search(r'name="__token__"\s+value="([^"]+)"', resp.text)
    if not match:
        raise RuntimeError("未能从登录页提取 __token__，页面结构可能已变化")
    token = match.group(1)
    print(f"[Token] 获取成功: {token[:16]}...")
    return token


def login(session):
    """执行登录，返回是否成功"""
    token = get_token(session)
    payload = {
        "account": ACCOUNT,
        "password": PASSWORD,
        "__token__": token,
    }
    resp = session.post(LOGIN_URL, data=payload, timeout=(10, 15), allow_redirects=False)
    # 登录成功通常会 302 跳转到用户首页
    if resp.status_code in (301, 302):
        print("[登录] 成功（302 跳转）")
        return True
    # 有些站点登录成功返回 200 但页面不含登录表单
    if resp.status_code == 200 and "登录" not in resp.text[:500]:
        print("[登录] 疑似成功（200 且无登录表单）")
        return True
    print(f"[登录] 失败，状态码: {resp.status_code}")
    return False


def expand(session):
    """访问扩容页面，每天仅一次有效"""
    resp = session.get(EXPAND_URL, timeout=(10, 15))
    resp.raise_for_status()

    if "每天仅可扩容一次" in resp.text:
        print("[扩容] ✅ 扩容成功！")
        return True, "扩容成功"
    elif "已经扩容" in resp.text or "今天已经" in resp.text:
        print("[扩容] ⚠️ 今日已扩容过")
        return True, "今日已扩容过（重复执行）"
    else:
        print("[扩容] ❌ 未知响应")
        return False, f"未知响应，页面内容前200字: {resp.text[:200]}"


def main():
    print(f"{'='*40}")
    print(f"img.ink 自动扩容 - 启动")
    if MANUAL_MODE:
        print("[模式] 手动触发，跳过随机延迟")
    print(f"{'='*40}")

    # 0. 检查是否被 Web 面板暂停（手动模式不受限）
    if not MANUAL_MODE:
        check_disabled()

    # 1. 随机延迟（手动模式跳过）
    if not MANUAL_MODE:
        random_wait()

    # 2. 创建会话并登录
    session = new_session()
    try:
        if not login(session):
            send_notify("img.ink 扩容失败", "登录失败，请检查账号密码或网站状态")
            sys.exit(1)
    except Exception as e:
        send_notify("img.ink 扩容失败", f"登录异常: {e}")
        raise

    # 3. 访问扩容页面
    try:
        success, msg = expand(session)
    except Exception as e:
        send_notify("img.ink 扩容失败", f"扩容请求异常: {e}")
        raise

    # 4. 邮件通知
    if success:
        send_notify("img.ink 扩容结果", f"执行完毕：{msg}")
    else:
        send_notify("img.ink 扩容失败", msg)

    print(f"{'='*40}")
    print("执行结束")
    print(f"{'='*40}")


if __name__ == "__main__":
    main()
