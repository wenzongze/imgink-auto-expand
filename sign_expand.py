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
# 容量核对用：一个「只读」的账户容量页面（不应触发扩容副作用）。
# 留空或与 EXPAND_URL 相同则改用本地基线文件（capacity_baseline.txt）做前后对比。
CAPACITY_URL = cfg["SETTING"].get("capacity_url", "").strip()
# 可选：自定义容量提取正则（留空则用内置的多格式匹配）
CAPACITY_REGEX = cfg["SETTING"].get("capacity_regex", "").strip()
BASELINE_FILE = os.path.join(BASE_DIR, "capacity_baseline.txt")
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


def parse_capacity(text):
    """从页面文本提取账户【总容量】，返回以 GB 为单位的 float；提取不到返回 None。

    img.ink 实际格式：'容量使用：\\n\\n45.02 MB / 9.94 GB'（已用 / 总容量）。
    优先取 '/' 后面的总容量；兜底再按关键词/单位通用匹配取最大值。
    """
    if not text:
        return None
    factor = {"TB": 1024.0, "T": 1024.0, "GB": 1.0, "G": 1.0, "MB": 1 / 1024.0, "M": 1 / 1024.0}
    to_gb = lambda num, unit: float(str(num).replace(",", "")) * factor.get(str(unit).upper(), 1.0)

    # 1) 优先：'已用 / 总容量' 形式，取 '/' 后面的总容量
    m = re.search(r'/\s*([\d,]+(?:\.\d+)?)\s*(GB|G|TB|T|MB|M)\b', text, re.IGNORECASE)
    if m:
        return to_gb(m.group(1), m.group(2))

    # 2) 自定义正则（config capacity_regex）
    if CAPACITY_REGEX:
        try:
            for m in re.finditer(CAPACITY_REGEX, text, re.IGNORECASE):
                try:
                    return to_gb(m.group(1), m.group(2))
                except (IndexError, ValueError):
                    continue
        except re.error:
            pass

    # 3) 兜底：通用匹配，取最大值（通常是总容量而非已用量）
    patterns = [
        r'(?:总容量|容量|存储空间|空间|存储)[^\d\n]{0,15}?([\d,]+(?:\.\d+)?)\s*(GB|G|TB|T|MB|M)\b',
        r'([\d,]+(?:\.\d+)?)\s*(GB|G|TB|T|MB|M)\b',
    ]
    values = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            values.append(to_gb(m.group(1), m.group(2)))
    if not values:
        return None
    return max(values)


def fetch_capacity(session, url, retries=3):
    """带重试地读取账户容量（GB）。读取失败或页面无容量数字时返回 None。"""
    last_err = "未知"
    for _ in range(retries):
        try:
            r = session.get(url, timeout=(10, 15))
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            cap = parse_capacity(r.text)
            if cap is not None:
                return cap
            last_err = "页面未包含容量数字"
        except Exception as e:
            last_err = f"读取容量异常: {e}"
            time.sleep(2)
    print(f"[容量] 获取失败（{last_err}），将依赖页面关键词判断。")
    return None


def read_baseline():
    """读取上次成功运行记录的容量基线（GB）。"""
    try:
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            return float(f.read().strip())
    except Exception:
        return None


def write_baseline(value):
    """写入本次容量作为新基线。"""
    try:
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            f.write(f"{value:.4f}")
    except Exception:
        pass


def expand(session):
    """访问扩容页面，每天仅一次有效。返回 (成功标志, 说明)。"""
    resp = session.get(EXPAND_URL, timeout=(10, 15))
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

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

    # 3. 扩容前的容量（优先读「只读」容量页；否则用本地基线文件）
    cap_before = None
    if CAPACITY_URL and CAPACITY_URL != EXPAND_URL:
        cap_before = fetch_capacity(session, CAPACITY_URL)
        if cap_before is not None:
            print(f"[容量] 扩容前: {cap_before:.2f} GB")
        else:
            print("[容量] 只读容量页未取到，改用本地基线对比")
    if cap_before is None:
        cap_before = read_baseline()
        print(f"[容量] 扩容前(基线): {cap_before:.2f} GB" if cap_before is not None
              else "[容量] 扩容前: 无基线（首次运行）")

    # 4. 执行扩容
    try:
        expand_success, expand_msg = expand(session)
    except Exception as e:
        send_notify("img.ink 扩容失败", f"扩容请求异常: {e}")
        raise

    # 5. 扩容后的容量（从扩容页读取，已是扩容后的状态）
    cap_after = fetch_capacity(session, EXPAND_URL)
    print(f"[容量] 扩容后: {cap_after:.2f} GB" if cap_after is not None
          else "[容量] 扩容后: 未取到")

    # 6. 依据容量是否真正增加来判定最终结果（只有增加才发「成功」）
    if cap_after is None:
        # 容量解析失败：退回页面关键词判断，但不轻易报「失败」
        if expand_success:
            send_notify("img.ink 扩容成功",
                        f"执行完毕：{expand_msg}（注：未能解析容量数字，依据页面关键词判定）")
        else:
            send_notify("img.ink 扩容提醒",
                        f"{expand_msg}（注：未能解析容量数字，无法确认是否成功，请登录网站确认）")
    elif cap_before is None:
        # 首次运行无基线：报告当前容量，无法证明「增加」
        send_notify("img.ink 扩容结果",
                    f"执行完毕：当前账户容量 {cap_after:.2f} GB（{expand_msg}，首次运行暂无前后对比）。")
        write_baseline(cap_after)
    elif cap_after > cap_before + 0.001:
        send_notify("img.ink 扩容成功",
                    f"执行完毕：账户容量由 {cap_before:.2f} GB 增加到 {cap_after:.2f} GB（{expand_msg}）。")
        write_baseline(cap_after)
    else:
        # 容量无变化
        if expand_success:
            send_notify("img.ink 扩容结果",
                        f"执行完毕：容量未变化（仍为 {cap_after:.2f} GB），但页面提示「{expand_msg}」，"
                        f"可能今日已扩容或无需扩容。")
        else:
            send_notify("img.ink 扩容提醒",
                        f"执行完毕：容量未变化（{cap_after:.2f} GB），且页面无成功标志：{expand_msg}。"
                        f"请登录网站确认是否已扩容。")
        write_baseline(cap_after)

    print(f"{'='*40}")
    print("执行结束")
    print(f"{'='*40}")


if __name__ == "__main__":
    main()
