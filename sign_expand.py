#!/usr/bin/env python3
"""img.ink 每日自动扩容签到脚本"""
import random
import time
import re
import configparser
import os
import sys
import json
from urllib.parse import urljoin
import glob as _glob
for _p in _glob.glob("/share/homes/*/.local/lib/python3*/site-packages"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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
STATE_FILE = os.path.join(BASE_DIR, "expand_state.json")  # 每日扩容状态记录（供 --check 自检）

# 容量差额自审（对应微软积分「积分差额」思路）：扩容前后各读一次容量页，
# 差额 > 0 即确认本次真的涨了容量，而非仅依赖页面「扩容成功」文案。
# capacity_url 留空则跳过差额自审（仅依赖文案+状态记录，等价原行为）。
CAPACITY_URL   = (cfg["SETTING"].get("capacity_url", "") or "").strip()
CAPACITY_REGEX = (cfg["SETTING"].get("capacity_regex", "") or "").strip()

# 容量差额自审前后读数（best-effort，读不到为 None）
CAP_BEFORE = None
CAP_AFTER = None

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


def _parse_capacity(text):
    """best-effort 从任意页面文本解析容量，统一返回 GB 浮点；解析不到返回 None。"""
    if not text:
        return None
    patterns = [CAPACITY_REGEX] if CAPACITY_REGEX else [
        r'(\d+(?:\.\d+)?)\s*(GB|TB|G|T)\b',
        r'容量[^\d]{0,8}(\d+(?:\.\d+)?)\s*(GB|TB|G|T)',
        r'(\d+(?:\.\d+)?)\s*([Gg]igabyte|[Tt]erabyte)',
    ]
    for p in patterns:
        try:
            m = re.search(p, text)
        except re.error:
            continue
        if m:
            val = float(m.group(1))
            unit = m.group(2).upper()
            if unit in ("TB", "T"):
                val *= 1024.0
            return val
    return None


def read_capacity(session):
    """best-effort 读取容量页容量（只读 capacity_url，绝不碰 EXPAND_URL 以免触发扩容副作用）。
    未配置 capacity_url 返回 None，绝不阻塞主流程。"""
    if not CAPACITY_URL:
        return None
    try:
        resp = session.get(CAPACITY_URL, timeout=(10, 15))
        resp.raise_for_status()
        cap = _parse_capacity(resp.text)
        print(f"[容量自审] 读取容量: {cap} GB" if cap is not None
              else "[容量自审] 容量页已读但未解析到容量（检查 capacity_regex）")
        return cap
    except Exception as e:  # noqa: BLE001
        print(f"[容量自审] 读取失败（已忽略）: {e}")
        return None


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


def _is_login_page(text):
    """判定页面是否仍是登录页（即未处于登录态）。
    关键：img.ink 未登录访问受保护页会被 302 跳回登录页，登录页面含密码输入框。"""
    if not text:
        return False
    low = text.lower()
    return bool(re.search(r'<input[^>]+type\s*=\s*["\']?password', low)) or \
           ("password" in low and "登录" in text)


def login(session):
    """执行登录，返回是否成功。

    关键坑：img.ink 登录【失败】同样返回 302 跳回登录页，因此【不能仅凭 302 判成功】。
    这里跟随跳转并核验落地页是否仍是登录表单——仍是登录页即视为登录失败，
    避免「假成功」导致后续扩容被踢回登录页、落进『未知响应』兜底。"""
    token = get_token(session)
    payload = {
        "account": ACCOUNT,
        "password": PASSWORD,
        "__token__": token,
    }
    resp = session.post(LOGIN_URL, data=payload, timeout=(10, 15), allow_redirects=False)
    # 跟随首跳到落地页（allow_redirects=False 仅拿首个 302，手动跟进以检查落地页）
    if resp.status_code in (301, 302):
        loc = (resp.headers.get("Location") or "").strip()
        if loc:
            if not loc.startswith("http"):
                loc = urljoin(LOGIN_URL, loc)
            try:
                land = session.get(loc, timeout=(10, 15))
            except Exception:  # noqa: BLE001
                land = resp
        else:
            land = resp
    else:
        land = resp
    if _is_login_page(land.text):
        print("[登录] ❌ 失败：提交后仍停留在登录页（账号/密码错误、或站点改版/验证码）")
        return False
    print("[登录] ✅ 成功（已脱离登录页，进入用户态）")
    return True


def expand(session):
    """访问扩容页面，每天仅一次有效。返回 (success, msg, cap_hint)。

    cap_hint 为从扩容成功页文本 best-effort 解析到的容量（可能 None），
    作为「容量自审」的辅助佐证；真正的差额校验以 read_capacity(capacity_url) 为准。
    """
    resp = session.get(EXPAND_URL, timeout=(10, 15))
    resp.raise_for_status()
    cap_hint = _parse_capacity(resp.text)

    # 关键：未登录访问受保护页会被踢回登录页（含密码框），需明确识别，
    # 避免与「未知响应」混淆，也便于 main() 触发重新登录自愈。
    if _is_login_page(resp.text):
        print("[扩容] ❌ 访问扩容页被重定向到登录页：会话未处于登录态")
        return False, "认证失败：访问扩容页被重定向到登录页，会话未处于登录态（登录态失效/登录未真正成功，请检查账号密码或站点是否改版）", None

    if "每天仅可扩容一次" in resp.text:
        print("[扩容] ✅ 扩容成功！")
        return True, "扩容成功", cap_hint
    elif "已经扩容" in resp.text or "今天已经" in resp.text:
        print("[扩容] ⚠️ 今日已扩容过")
        return True, "今日已扩容过（重复执行）", cap_hint
    else:
        print("[扩容] ❌ 未知响应")
        return False, f"未知响应，页面内容前200字: {resp.text[:200]}", None


def record_state(done, capacity, note):
    """记录今日扩容结果（成功/失败 + 提示），供 --check 自检判断。

    动机：扩容脚本「跑完即认为成功」，但站点可能静默没真扩容、登录态失效、
    或「今日已扩容」误判。有了每日状态，自检才能区分「今天还没到执行窗口」
    和「今天确实没成功」，避免白天误报警、深夜真漏做却没人知道。
    """
    try:
        data = {
            "date": time.strftime("%Y-%m-%d"),
            "done": bool(done),
            "capacity": (float(capacity) if capacity is not None else None),
            "note": note or "",
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[状态] 写入 {STATE_FILE} 失败: {e}")


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

    # 3. 容量自审：扩容前读一次容量（仅当配置了 capacity_url）
    if CAPACITY_URL:
        try:
            CAP_BEFORE = read_capacity(session)
            print(f"[容量自审] 扩容前容量：{CAP_BEFORE} GB")
        except Exception as e:  # noqa: BLE001
            print(f"[容量自审] 扩容前读数失败（已忽略）: {e}")

    # 4. 访问扩容页面（带一次认证自愈：若被踢回登录页，重登录后重试一次）
    try:
        success, msg, cap_hint = expand(session)
    except Exception as e:
        send_notify("img.ink 扩容失败", f"扩容请求异常: {e}")
        raise
    if not success and "认证失败" in msg:
        print("[扩容] 检测到未登录，尝试重新登录并自愈一次...")
        try:
            if login(session):
                success, msg, cap_hint = expand(session)
                print("[扩容] 自愈重试完成")
            else:
                print("[扩容] 自愈失败：重新登录仍未成功")
        except Exception as e:  # noqa: BLE001
            print(f"[扩容] 自愈异常（已忽略）: {e}")

    # 5. 容量自审：扩容后读一次容量，确认是否真的涨了
    cap_note = ""
    cap_record = cap_hint
    if CAPACITY_URL:
        try:
            CAP_AFTER = read_capacity(session)
            cap_record = CAP_AFTER
        except Exception:  # noqa: BLE001
            CAP_AFTER = None
        if CAP_BEFORE is not None and CAP_AFTER is not None:
            delta = CAP_AFTER - CAP_BEFORE
            cap_note = f" | 容量自审 {CAP_BEFORE}GB→{CAP_AFTER}GB (Δ{delta:+.1f})"
            cap_note += " [确认真扩容]" if delta > 0 else " [容量未变：可能已含今日额度或延迟入账]"
        elif cap_hint is not None:
            cap_note = f" | 扩容页解析容量 {cap_hint}GB（仅页面佐证）"
        else:
            cap_note = " | 容量页未解析到数值，差额自审不可用"
    else:
        cap_note = " | 未配置 capacity_url，仅依赖文案+状态记录（建议配置以启用容量差额自审）"

    # 6. 邮件通知
    if success:
        send_notify("img.ink 扩容结果", f"执行完毕：{msg}{cap_note}")
    else:
        send_notify("img.ink 扩容失败", f"{msg}{cap_note}")

    # 记录今日扩容状态（供 --check 自检判断「今天到底做没做」，并保存容量读数）
    record_state(bool(success), cap_record, msg + cap_note)

    print(f"{'='*40}")
    print("执行结束")
    print(f"{'='*40}")


def verify_mode():
    """只读自检：判断「今天是否已经成功扩容」，不二次触发扩容副作用。

    用法：python sign_expand.py --check  （或 --verify / -c）

    判定（避免白天误报警 / 深夜真漏做没人知道）：
      · 今日状态文件（expand_state.json）显示 done → ✅；
      · 还没到随机窗口末（RANDOM_END:00）→ ⏳ 正常，计划任务稍后会跑，不打扰；
      · 已过窗口且无今日成功记录 → ❌ 真漏做，发告警邮件。
    注意：本站 config.ini 未配置 capacity_url，自检以「状态记录 + 窗口时刻」为准；
    若日后配置了容量页，可在本函数内补充容量比对。
    """
    print("=" * 40)
    print("img.ink 扩容自检 - 启动（只读，不重复扩容）")
    print("=" * 40)
    session = new_session()
    try:
        if not login(session):
            print("[自检] ❌ 登录失败，无法核验今日是否扩容")
            send_notify("img.ink 扩容自检", "登录失败，无法核验今日扩容是否完成，请检查账号或网站状态。")
            sys.exit(1)
    except Exception as e:
        print(f"[自检] 登录异常: {e}")
        sys.exit(1)

    # 读取今日状态记录
    state = {}
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)
    except Exception as e:
        print(f"[自检] 读取状态记录失败: {e}")

    today = time.strftime("%Y-%m-%d")
    now = time.localtime()
    current_minutes = now.tm_hour * 60 + now.tm_min
    end_minutes = RANDOM_END * 60

    ok = True
    verdict = ""
    detail = ""
    if state.get("date") == today and state.get("done"):
        verdict = "✅ 今日已成功扩容"
        cap = state.get("capacity")
        cap_str = f" | 容量读数: {cap} GB" if cap is not None else ""
        detail = f"记录: {state.get('note','')}{cap_str}"
    elif current_minutes <= end_minutes:
        verdict = f"⏳ 今日尚未到执行窗口末（{RANDOM_END}:00）"
        detail = (f"当前 {now.tm_hour:02d}:{now.tm_min:02d}，随机窗口至 {RANDOM_END}:00，"
                  f"计划任务会在窗口内随机触发，暂无需告警。")
    else:
        verdict = "❌ 今日尚未完成扩容"
        detail = (f"已过随机窗口末（{RANDOM_END}:00）且无今日成功记录。"
                  f"可点面板「立即执行」手动补跑，或检查 cron / 登录态 / disabled.flag。")
        ok = False

    print(f"[自检] {verdict} —— {detail}")

    # 仅当「确实未完成」才发告警（白天/窗口内不打扰）
    if not ok:
        send_notify("img.ink 扩容自检未通过", f"{verdict}：{detail}")

    print("=" * 40)
    print("自检结束")
    print("=" * 40)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--check" in sys.argv or "--verify" in sys.argv or "-c" in sys.argv:
        verify_mode()
    else:
        main()
