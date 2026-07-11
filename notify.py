#!/usr/bin/env python3
"""邮件通知模块"""
import smtplib
import configparser
import os
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cfg = configparser.ConfigParser()
cfg.read(os.path.join(BASE_DIR, "config.ini"), encoding="utf-8")

SMTP_SERVER = cfg["MAIL"]["smtp_server"]
SMTP_PORT   = int(cfg["MAIL"]["smtp_port"])
SENDER      = cfg["MAIL"]["sender"]
AUTH_CODE   = cfg["MAIL"]["auth_code"]
RECEIVER    = cfg["MAIL"]["receiver"]


def send_notify(subject, content):
    """发送邮件通知"""
    # 检查是否配置了邮箱
    if "你的邮箱" in SENDER or not AUTH_CODE.strip():
        print(f"[通知] 邮箱未配置，跳过发送。内容: {subject} - {content}")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = MIMEText(f"{content}\n\n执行时间: {now_str}", "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = SENDER
    msg["To"] = RECEIVER

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=15)
        server.login(SENDER, AUTH_CODE)
        server.sendmail(SENDER, [RECEIVER], msg.as_string())
        server.quit()
        print(f"[邮件] 发送成功 -> {RECEIVER}")
    except Exception as e:
        print(f"[邮件] 发送失败: {e}")


if __name__ == "__main__":
    send_notify("测试邮件", "这是一封来自 img.ink 自动扩容脚本的测试邮件")
