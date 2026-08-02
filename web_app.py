#!/usr/bin/env python3
"""img.ink 自动扩容 - Web 可视化管理面板"""
import os
import sys

# 确保能找到用户目录 (/share/homes/Mars/.local) 下安装的 requests / flask
_LOCAL_SITE = '/share/homes/Mars/.local/lib/python3.12/site-packages'
if _LOCAL_SITE not in sys.path:
    sys.path.insert(0, _LOCAL_SITE)

import subprocess
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISABLED_FLAG = os.path.join(BASE_DIR, "disabled.flag")
SCRIPT_PATH = os.path.join(BASE_DIR, "sign_expand.py")
TITLE_FILE = os.path.join(BASE_DIR, "title.txt")
DEFAULT_TITLE = "🖼️ img.ink 自动扩容"
JOBNAMES_FILE = os.path.join(BASE_DIR, "jobnames.json")


def get_panel_title():
    """读取已保存的面板标题，无则使用默认"""
    try:
        if os.path.exists(TITLE_FILE):
            with open(TITLE_FILE, "r", encoding="utf-8") as f:
                t = f.read().strip()
            if t:
                return t
    except Exception:
        pass
    return DEFAULT_TITLE


def set_panel_title(title):
    """保存面板标题到文件"""
    title = (title or "").strip()
    if not title:
        raise ValueError("标题不能为空")
    with open(TITLE_FILE, "w", encoding="utf-8") as f:
        f.write(title)


def get_job_names():
    """读取任务自定义名称映射：{command: 自定义名}"""
    try:
        if os.path.exists(JOBNAMES_FILE):
            with open(JOBNAMES_FILE, "r", encoding="utf-8") as f:
                return json.loads(f.read()) or {}
    except Exception:
        pass
    return {}


def set_job_name(command, name):
    """保存某个任务的自定义名称（按 command 唯一标识）"""
    name = (name or "").strip()
    data = get_job_names()
    if not name:
        # 清空即恢复默认
        data.pop(command, None)
    else:
        data[command] = name
    with open(JOBNAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- Flask check ---
try:
    from flask import Flask, render_template_string, jsonify, request
except ImportError:
    print("请先安装 Flask: pip3 install flask")
    sys.exit(1)

app = Flask(__name__)

# ------------------------------------------------------------
# HTML 模板（内嵌，无需额外文件）
# ------------------------------------------------------------
TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }} - 管理面板</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f1419; color: #e7e9ea; min-height: 100vh;
  }
  .container{max-width: 800px; margin: 0 auto; padding: 30px 20px;}
  .header{
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 30px; padding-bottom: 20px;
    border-bottom: 1px solid #2f3336;
  }
  .header h1{font-size: 22px; font-weight: 700; color: #fff;}
  .header h1:hover::after{content:" ✎"; font-size:14px; color:#1d9bf0; vertical-align:middle;}
  .header .time{font-size: 13px; color: #71767b;}
  .title-editor{
    display:flex; align-items:center; gap:8px; flex-wrap:wrap;
  }
  .title-editor input{
    font-size: 18px; font-weight: 700; color: #fff;
    background: #0d1117; border: 1px solid #1d9bf0; border-radius: 8px;
    padding: 4px 10px; min-width: 220px; outline: none;
  }
  .btn-mini{
    padding: 6px 14px; border: none; border-radius: 999px;
    font-size: 13px; font-weight: 600; cursor: pointer; color: #fff;
    transition: filter .15s ease;
  }
  .btn-mini:hover{ filter: brightness(1.1); }
  .btn-save{background:#00ba7c;} .btn-save:hover{background:#00a06b;}
  .btn-cancel{background:#2f3336;} .btn-cancel:hover{background:#3e4146;}
  .job-name-editor{
    display:inline-flex; align-items:center; gap:8px; flex-wrap:wrap;
  }
  .job-name-editor input{
    font-size: 15px; font-weight: 700; color: #fff;
    background: #0d1117; border: 1px solid #1d9bf0; border-radius: 8px;
    padding: 4px 10px; min-width: 200px; outline: none;
    box-shadow: 0 0 0 3px rgba(29,155,240,.15);
  }
  .job-name-editor input:focus{ border-color: #1d9bf0; }
  .job-name-editor .btn-mini{ padding: 5px 12px; }
  .cards{display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px;}
  .card{
    background: #1a1f26; border-radius: 12px; padding: 20px;
    border: 1px solid #2f3336;
  }
  .card .label{font-size: 12px; color: #71767b; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;}
  .card .value{font-size: 28px; font-weight: 700;}
  .card .sub{font-size: 12px; color: #71767b; margin-top: 6px;}
  .status-on{color: #00ba7c;}
  .status-off{color: #f4212e;}
  .status-running{color: #1d9bf0;}
  .btn-group{display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap;}
  .btn{
    display: flex; align-items: center; gap: 8px;
    padding: 10px 20px; border: none; border-radius: 999px;
    font-size: 14px; font-weight: 600; cursor: pointer;
    transition: all 0.2s; color: #fff;
  }
  .btn-run{background: #1d9bf0;}
  .btn-run:hover{background: #1a8cd8;}
  .btn-run:disabled{opacity: .5; cursor: not-allowed;}
  .btn-toggle{background: #00ba7c;}
  .btn-toggle:hover{background: #00a06b;}
  .btn-toggle.off{background: #f4212e;}
  .btn-toggle.off:hover{background: #da1f2b;}
  .btn-refresh{background: #2f3336;}
  .btn-refresh:hover{background: #3e4146;}
  .btn-restart{background: #1d9bf0;}
  .btn-restart:hover{background: #1a8cd8;}
  .btn-restart:disabled{opacity: .6; cursor: default;}
  .btn-selfcheck{background: #7856ff;}
  .btn-selfcheck:hover{background: #6a4be0;}
  .self-check{
    background: #1a1f26; border: 1px solid #2f3336; border-radius: 12px;
    padding: 16px 18px; margin-bottom: 24px; font-size: 13px; line-height: 1.8;
  }
  .self-check h3{font-size: 14px; color:#fff; margin-bottom: 10px; font-weight:700;}
  .self-check .row{display:flex; align-items:center; gap:8px; flex-wrap:wrap;}
  .self-check .tag{
    display:inline-flex; align-items:center; gap:5px;
    padding:3px 10px; border-radius:999px; font-weight:600; font-size:12px;
  }
  .self-check .ok{background:#06301f; color:#00ba7c;}
  .self-check .bad{background:#3a0d11; color:#f4212e;}
  .self-check .label{color:#8b96a0;}
  .self-check .val{color:#e7e9ea; font-family:"Cascadia Code","Fira Code",monospace; word-break:break-all;}
  .self-check .hint{color:#71767b; margin-top:10px; font-size:12px; line-height:1.6;}
  body.light .self-check{background:#fff; border-color:#e1e5ea;}
  body.light .self-check h3{color:#0f1419;}
  body.light .self-check .label{color:#536471;}
  body.light .self-check .val{color:#1a1f26;}
  body.light .self-check .hint{color:#657786;}
  .btn-log{background: #2f3336;}
  .btn-log:hover{background: #3e4146;}
  .log-box{
    background: #000; border-radius: 12px; padding: 16px;
    border: 1px solid #2f3336; font-family: "Cascadia Code", "Fira Code", monospace;
    font-size: 12px; max-height: 400px; overflow-y: auto; line-height: 1.6;
    white-space: pre-wrap; word-break: break-all; color: #b0b8b8;
  }
  .log-box .ok{color: #00ba7c;}
  .log-box .warn{color: #ffd700;}
  .log-box .err{color: #f4212e;}
  .log-box .info{color: #1d9bf0;}
  .running-indicator{
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    margin-right: 6px; animation: pulse 1.5s infinite;
  }
  .running-indicator.active{background: #1d9bf0;}
  .running-indicator.idle{background: #71767b;}
  @keyframes pulse{
    0%,100%{opacity:1}50%{opacity:.3}
  }
  .empty-state{text-align: center; padding: 40px; color: #71767b;}
  .empty-state .icon{font-size: 48px; margin-bottom: 12px;}
  .section-title{
    font-size: 15px; font-weight: 600; color: #fff;
    margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;
  }
  .cron-table{
    width: 100%; border-collapse: collapse; margin-bottom: 8px;
    font-size: 12px;
  }
  .cron-table th{
    text-align: left; padding: 8px 10px; color: #71767b;
    border-bottom: 1px solid #2f3336; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .cron-table td{
    padding: 8px 10px; border-bottom: 1px solid #1f242b;
    vertical-align: top; word-break: break-all;
  }
  .cron-table tr:hover td{background: #161b22;}
  .cron-sched{color: #1d9bf0; font-family: "Cascadia Code","Fira Code",monospace; white-space: nowrap;}
  .cron-cmd{color: #b0b8b8; font-family: "Cascadia Code","Fira Code",monospace;}
  .tag-imgink{
    display: inline-block; margin-left: 6px; padding: 1px 7px; border-radius: 999px;
    background: #00ba7c; color: #06281c; font-size: 10px; font-weight: 700; vertical-align: middle;
  }
  .sub-title{
    font-size: 13px; color: #71767b; margin: 18px 0 10px;
    display: flex; align-items: center; gap: 6px;
  }
  .collapsible-head{
    cursor: pointer; user-select: none;
    background: #161b22; border: 1px solid #2f3336; border-radius: 10px;
    padding: 10px 14px; margin-bottom: 10px; color: #e7e9ea; font-weight: 600;
    transition: background .2s;
  }
  .collapsible-head:hover{background: #1a2029;}
  .collapsed{display: none;}
  .job-card{
    background: #1a1f26; border: 1px solid #2f3336; border-radius: 12px;
    padding: 16px; margin-bottom: 12px;
  }
  .job-card.system{border-color: #232a33; opacity: .85;}
  .job-head{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap;}
  .job-name{font-size: 15px; font-weight: 700; color: #fff; display:flex; align-items:center; gap:8px;}
  .job-sched{
    font-family: "Cascadia Code","Fira Code",monospace; font-size: 12px;
    color: #1d9bf0; background: #11202e; padding: 4px 10px; border-radius: 999px;
    white-space: nowrap;
  }
  .job-desc{font-size: 12px; color: #8b96a0; margin-top: 10px; line-height: 1.6;}
  .job-cmd{
    font-family: "Cascadia Code","Fira Code",monospace; font-size: 11px;
    color: #5b656f; margin-top: 8px; word-break: break-all;
    background:#0d1117; padding:6px 8px; border-radius:6px;
  }
  .job-actions{margin-top: 12px;}
  .btn-job{
    display:inline-flex; align-items:center; gap:6px;
    padding: 7px 16px; border:none; border-radius:999px;
    font-size: 13px; font-weight:600; cursor:pointer; color:#fff;
    background:#1d9bf0; transition: all .2s;
  }
  .btn-job:hover{background:#1a8cd8;}
  .btn-job:disabled{opacity:.5; cursor:not-allowed;}
  .btn-log{background:#2f3336;}
  .btn-log:hover{background:#3e4146;}
  .job-log{
    margin-top: 10px; background:#000; border:1px solid #2f3336;
    border-radius:8px; padding:10px; max-height:280px; overflow:auto;
  }
  .job-log.collapsed{display:none;}
  .job-log-pre{
    margin:0; font-family:"Cascadia Code","Fira Code",monospace;
    font-size:11px; line-height:1.5; color:#c9d1d9; white-space:pre-wrap; word-break:break-all;
  }
  .job-log-empty{color:#71767b; font-size:12px; padding:4px 0;}
  .badge{
    display:inline-block; padding:2px 9px; border-radius:999px;
    font-size:10px; font-weight:700; vertical-align:middle;
  }
  .badge-auto{background:#00ba7c; color:#06281c;}
  .badge-sys{background:#3e4146; color:#c9d1d9;}
  .badge-run{background:#1d9bf0; color:#04243b;}
  @media (max-width: 600px){
    .cards{grid-template-columns: 1fr;}
    .header{flex-direction: column; align-items: flex-start; gap: 8px;}
  }

  /* 悬浮按钮：日间/夜间 + 回到顶部（向下滚动隐藏，向上滚动显示） */
  .fab-group{
    position: fixed; right: 20px; bottom: 24px; z-index: 999;
    display: flex; flex-direction: column; gap: 12px;
    transition: opacity .3s, transform .3s;
  }
  .fab-group.hidden{opacity: 0; transform: translateY(20px); pointer-events: none;}
  .fab{
    width: 46px; height: 46px; border-radius: 50%; border: 1px solid #2f3336;
    background: #1a1f26; color: #e7e9ea; font-size: 20px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 4px 14px rgba(0,0,0,.4); transition: all .2s;
  }
  .fab:hover{background: #2f3336; transform: scale(1.08);}

  /* 日间模式配色（body.light 时生效） */
  body.light{
    background: #f5f7fa; color: #1a1f26;
  }
  body.light .header{border-bottom-color:#e1e5ea;}
  body.light .header h1{color:#0f1419;}
  body.light .header .time{color:#657786;}
  body.light .section-title{color:#0f1419;}
  body.light .sub-title{color:#657786;}
  body.light .card,
  body.light .job-card{background:#fff; border-color:#e1e5ea;}
  body.light .job-card.system{border-color:#eef1f4; opacity:.9;}
  body.light .job-desc{color:#536471;}
  body.light .job-cmd{color:#8b96a0; background:#f0f3f5;}
  body.light .job-name{color:#0f1419;}
  body.light .job-name-editor input{ background:#fff; color:#0f1419; border-color:#1d9bf0; box-shadow:none; }
  body.light .collapsible-head{background:#eef1f4; border-color:#e1e5ea; color:#1a1f26;}
  body.light .collapsible-head:hover{background:#e4e8ec;}
  body.light .cron-table th{color:#657786; border-bottom-color:#e1e5ea;}
  body.light .cron-table td{border-bottom-color:#eef1f4;}
  body.light .cron-table tr:hover td{background:#f7f9fa;}
  body.light .cron-cmd{color:#536471;}
  body.light .badge-sys{background:#e1e5ea; color:#536471;}
  body.light .log-box,
  body.light .job-log{background:#111; border-color:#e1e5ea;}
  body.light .fab{background:#fff; color:#1a1f26; border-color:#e1e5ea;}
  body.light .fab:hover{background:#f0f3f5;}
  body.light .job-log-empty{color:#657786;}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1 id="panelTitle" title="点击修改标题" style="cursor:pointer;outline:none;"
        onclick="startEditTitle()">{{ title }}</h1>
    <span class="time" id="currentTime">--</span>
  </div>

  <div class="btn-group" style="margin-bottom:24px;">
    <button class="btn btn-toggle" id="btnToggle" onclick="toggleCron()">
      ⏸ 暂停计划任务
    </button>
    <button class="btn btn-refresh" onclick="loadStatus()">🔄 刷新</button>
    <button class="btn btn-selfcheck" id="btnSelfCheck" onclick="runSelfCheck()">🔍 页面自检</button>
    <button class="btn btn-restart" id="btnRestart" onclick="restartPanel()">♻️ 重启面板</button>
    <button class="btn btn-selfcheck" id="btnExpandCheck" onclick="runExpandCheck()">✅ 扩容自检</button>
  </div>

  <div id="selfCheckBox" class="self-check" style="display:none;"></div>
  <div id="expandCheckBox" class="self-check" style="display:none; margin-top:12px;"></div>

  <div class="section-title" style="margin-top:10px;">
    📋 全部计划任务
    <span style="font-size:12px;color:#71767b;font-weight:400;" id="cronJobCount">--</span>
  </div>
  <div class="sub-title">⭐ 我的自动执行任务</div>
  <div id="userJobList"></div>
  <div class="sub-title collapsible-head" id="sysHead" onclick="toggleSysJobs()">
    <span>⚙️ 系统任务（只读）</span>
    <span id="sysToggle" style="margin-left:auto;font-size:12px;color:#1d9bf0;">▾ 收起</span>
  </div>
  <div id="sysJobList"></div>
</div>

<!-- 悬浮按钮：日间/夜间切换 + 回到顶部 -->
<div class="fab-group hidden" id="fabGroup">
  <button class="fab" id="fabTheme" title="切换日间/夜间模式" onclick="toggleTheme()">🌙</button>
  <button class="fab" id="fabTop" title="回到顶部" onclick="goTop()">⬆️</button>
</div>

<script>
let pollingTimer = null;
let isRunning = false;

function fmtTime(ts) {
  if (!ts) return '--';
  const d = new Date(ts);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// 行内编辑面板标题（点击标题进入编辑态，回车保存 / Esc 取消）
function startEditTitle() {
  const h1 = document.getElementById('panelTitle');
  if (!h1 || h1.dataset.editing === '1') return;
  h1.dataset.editing = '1';
  const current = h1.dataset.title || h1.textContent;
  const editor = document.createElement('span');
  editor.className = 'title-editor';
  editor.innerHTML =
    `<input id="titleInput" type="text" maxlength="40" value="${escapeHtml(current)}">` +
    `<button class="btn-mini btn-save" onclick="saveTitle(event)">保存</button>` +
    `<button class="btn-mini btn-cancel" onclick="cancelEditTitle(event)">取消</button>`;
  h1.replaceWith(editor);
  const input = document.getElementById('titleInput');
  input.focus();
  input.select();
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); saveTitle(e); }
    else if (e.key === 'Escape') { e.preventDefault(); cancelEditTitle(e); }
  });
}

function cancelEditTitle(e) {
  e && e.stopPropagation();
  restoreTitleEl();
}

function restoreTitleEl() {
  const editor = document.querySelector('.title-editor');
  if (!editor) return;
  const h1 = document.createElement('h1');
  h1.id = 'panelTitle';
  h1.title = '点击修改标题';
  h1.style.cssText = 'cursor:pointer;outline:none;';
  h1.dataset.title = document.getElementById('titleInput').value;
  h1.textContent = h1.dataset.title;
  h1.onclick = startEditTitle;
  editor.replaceWith(h1);
}

async function saveTitle(e) {
  e && e.stopPropagation();
  const input = document.getElementById('titleInput');
  const newTitle = input.value.trim();
  if (!newTitle) { alert('标题不能为空'); input.focus(); return; }
  try {
    const resp = await fetch('/api/set-title', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle })
    });
    const data = await resp.json();
    if (data.success) {
      const h1 = document.createElement('h1');
      h1.id = 'panelTitle';
      h1.title = '点击修改标题';
      h1.style.cssText = 'cursor:pointer;outline:none;';
      h1.dataset.title = newTitle;
      h1.textContent = newTitle;
      h1.onclick = startEditTitle;
      document.querySelector('.title-editor').replaceWith(h1);
      document.title = newTitle + ' - 管理面板';
    } else {
      alert('保存失败：' + (data.error || '未知错误'));
    }
  } catch(err) {
    alert('请求失败: ' + err);
  }
}

// 行内编辑某条 cron 任务的名称（点击任务名进入编辑态，回车保存 / Esc 取消）
// command 从 window.__cronJobs[gIdx] 取，避免把含特殊字符的命令拼进 HTML 属性
function startEditJobName(gIdx) {
  const job = (window.__cronJobs || [])[gIdx];
  if (!job) return;
  const command = job.command;
  const el = document.querySelector(`.job-card .job-name[onclick*="startEditJobName(${gIdx})"]`);
  if (!el || el.dataset.editing === '1') return;
  el.dataset.editing = '1';
  const current = job.custom_name || job.name;
  const editor = document.createElement('span');
  editor.className = 'job-name-editor';
  editor.innerHTML =
    `<input id="jobNameInput_${gIdx}" type="text" maxlength="40" value="${escapeHtml(current)}">` +
    `<button class="btn-mini btn-save" onclick="saveJobName(event, ${gIdx})">保存</button>` +
    `<button class="btn-mini btn-cancel" onclick="cancelEditJobName(event, ${gIdx})">取消</button>`;
  el.replaceWith(editor);
  const input = document.getElementById('jobNameInput_' + gIdx);
  input.focus();
  input.select();
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); saveJobName(e, gIdx); }
    else if (e.key === 'Escape') { e.preventDefault(); cancelEditJobName(e, gIdx); }
  });
}

function cancelEditJobName(e, gIdx) {
  e && e.stopPropagation();
  const editor = document.getElementById('jobNameInput_' + gIdx)?.parentElement;
  if (editor) editor.replaceWith(buildJobNameEl(gIdx));
}

function buildJobNameEl(gIdx) {
  const j = (window.__cronJobs || [])[gIdx];
  if (!j) return document.createElement('span');
  const badge = j.system
    ? '<span class="badge badge-sys">系统</span>'
    : '<span class="badge badge-auto">自动</span>';
  const span = document.createElement('span');
  span.className = 'job-name';
  span.title = '点击修改名称';
  span.style.cssText = 'cursor:pointer;';
  span.dataset.name = j.custom_name || j.name;
  span.innerHTML = escapeHtml(j.custom_name || j.name) + ' ' + badge;
  span.onclick = () => startEditJobName(gIdx);
  return span;
}

async function saveJobName(e, gIdx) {
  e && e.stopPropagation();
  const job = (window.__cronJobs || [])[gIdx];
  const command = job ? job.command : '';
  const input = document.getElementById('jobNameInput_' + gIdx);
  const newName = input.value.trim();
  try {
    const resp = await fetch('/api/set-job-name', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: command, name: newName })
    });
    const data = await resp.json();
    if (data.success) {
      if (!window.__cronJobs) window.__cronJobs = [];
      window.__cronJobs[gIdx] = Object.assign({}, window.__cronJobs[gIdx], { custom_name: data.name });
      const editor = input.parentElement;
      editor.replaceWith(buildJobNameEl(gIdx));
    } else {
      alert('保存失败：' + (data.error || '未知错误'));
    }
  } catch(err) {
    alert('请求失败: ' + err);
  }
}


// 页面自检：绕过 F12 验证陷阱，直接在页面上显示关键样式/功能是否加载
async function runSelfCheck() {
  const box = document.getElementById('selfCheckBox');
  const btn = document.getElementById('btnSelfCheck');
  btn.disabled = true; btn.textContent = '⏳ 检测中...';

  const rows = [];
  const tag = (ok) => ok
    ? '<span class="tag ok">✅ 正常</span>'
    : '<span class="tag bad">❌ 缺失</span>';

  // 1) job-name-editor 样式是否在本页 style 中
  const styles = [...document.querySelectorAll('style')];
  const jne = styles.some(s => s.textContent.includes('job-name-editor'));
  rows.push(`<div class="row"><span class="label">任务名编辑框样式</span> ${tag(jne)}
      <span class="val">(style 标签 ${styles.length} 个，命中 ${jne ? 1 : 0})</span></div>`);

  // 2) btn-mini 美化样式（保存/取消按钮）是否加载
  const bmini = styles.some(s => s.textContent.includes('.btn-mini'));
  rows.push(`<div class="row"><span class="label">保存/取消按钮样式</span> ${tag(bmini)}
      <span class="val">(.btn-mini 规则 ${bmini ? '已注入' : '未找到'})</span></div>`);

  // 3) 向服务器重新拉取原始 HTML，确认服务器当前吐出的页面是否含新样式
  let serverOk = null, serverInfo = '';
  try {
    const resp = await fetch(location.href, { cache: 'no-store' });
    const html = await resp.text();
    serverOk = html.includes('job-name-editor');
    serverInfo = serverOk ? '服务器已返回新页面' : '服务器仍是旧页面';
  } catch(e) {
    serverInfo = '请求服务器失败: ' + e;
  }
  rows.push(`<div class="row"><span class="label">服务器最新页面</span> ${tag(serverOk)}
      <span class="val">(${serverInfo})</span></div>`);

  // 4) 本地 DOM 与服务端是否一致（不一致说明浏览器在用旧 DOM）
  let consistent = (jne === serverOk);
  rows.push(`<div class="row"><span class="label">本地 DOM ↔ 服务器一致</span> ${tag(consistent)}
      <span class="val">(${consistent ? '一致' : '不一致：浏览器可能用了缓存/旧标签'})</span></div>`);

  // 5) 关键接口是否可达
  let apiOk = null;
  try {
    const r = await fetch('/api/status', { cache: 'no-store' });
    apiOk = r.ok;
  } catch(e) { apiOk = false; }
  rows.push(`<div class="row"><span class="label">后端接口 /api/status</span> ${tag(apiOk)}
      <span class="val">(${apiOk ? '正常' : '不可用'})</span></div>`);

  const allOk = jne && bmini && serverOk && consistent && apiOk;
  let hint = '';
  if (allOk) {
    hint = '🎉 全部正常：任务名编辑框与保存/取消按钮样式均已生效，无需重启。';
  } else if (!serverOk) {
    hint = '服务器还返回旧页面 —— 请点「♻️ 重启面板」让新代码生效；若已重启仍如此，检查是否改错了 web_app.py 文件。';
  } else if (!consistent) {
    hint = '服务器已是新页面，但本标签 DOM 仍是旧的 —— 请<b>按 Ctrl+Shift+R 强制刷新</b>，或新建标签页手动输入地址打开。';
  } else {
    hint = '本地样式缺失但服务器正常，通常是浏览器扩展注入了多余 style 标签或缓存了旧 CSS，请强制刷新(Ctrl+Shift+R)后重试。';
  }

  box.innerHTML =
    `<h3>🔍 页面自检结果</h3>` + rows.join('') +
    `<div class="hint">${hint}</div>`;
  box.style.display = 'block';
  btn.disabled = false; btn.textContent = '🔍 页面自检';
}

// 扩容自检：调后端 /api/check-expand，判断「今天是否真的扩容成功」
async function runExpandCheck() {
  const box = document.getElementById('expandCheckBox');
  const btn = document.getElementById('btnExpandCheck');
  btn.disabled = true; btn.textContent = '⏳ 自检中...';
  box.style.display = 'block';
  box.innerHTML = '<h3>✅ 扩容自检</h3><div class="row"><span class="label">状态</span> <span class="tag">⏳ 核验中...</span></div>';
  try {
    const resp = await fetch('/api/check-expand', { method: 'POST' });
    const data = await resp.json();
    if (!data.success) {
      box.innerHTML = `<h3>✅ 扩容自检</h3><div class="row"><span class="label">结果</span> <span class="tag bad">❌ 请求失败</span> <span class="val">${escapeHtml(data.error || '')}</span></div>`;
    } else {
      const ok = data.ok;
      const cls = ok ? 'ok' : 'bad';
      const icon = ok ? '✅ 通过' : '❌ 未通过';
      const esc = escapeHtml(data.result);
      box.innerHTML = `<h3>✅ 扩容自检结果</h3>`
        + `<div class="row"><span class="label">结论</span> <span class="tag ${cls}">${icon}</span> <span class="val">(exit ${data.exit_code})</span></div>`
        + `<div class="hint"><pre class="job-log-pre" style="white-space:pre-wrap;word-break:break-all;">${esc}</pre></div>`;
    }
  } catch (e) {
    box.innerHTML = `<h3>✅ 扩容自检</h3><div class="row"><span class="label">结果</span> <span class="tag bad">❌ 异常</span> <span class="val">${escapeHtml(String(e))}</span></div>`;
  } finally {
    btn.disabled = false; btn.textContent = '✅ 扩容自检';
  }
}

async function loadStatus() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();

    // Current time
    document.getElementById('currentTime').textContent = fmtTime(Date.now());

    // Cron 启用状态（驱动暂停/启用按钮）
    const toggleBtn = document.getElementById('btnToggle');
    if (data.cron_active) {
      toggleBtn.textContent = '⏸ 暂停计划任务';
      toggleBtn.className = 'btn btn-toggle off';
    } else {
      toggleBtn.textContent = '▶ 启用计划任务';
      toggleBtn.className = 'btn btn-toggle';
    }

    // 渲染全部 cron 任务（分为「我的任务」与「系统任务」两组）
    const jobs = data.cron_jobs || [];
    window.__cronJobs = jobs;  // 供任务名行内编辑使用
    document.getElementById('cronJobCount').textContent = jobs.length + ' 条';
    const userList = document.getElementById('userJobList');
    const sysList = document.getElementById('sysJobList');

    // renderCard 使用「任务在全量 jobs 中的全局下标」作为按钮回调参数
    const renderCard = (j, gIdx) => {
      const badge = j.system
        ? '<span class="badge badge-sys">系统</span>'
        : '<span class="badge badge-auto">自动</span>';
      const cmd = escapeHtml(j.command.length > 160 ? j.command.slice(0, 160) + '…' : j.command);
      const runBtn = j.runnable
        ? `<button class="btn-job" id="jobRun_${gIdx}" onclick="runJobByIndex(${gIdx})">▶ 立即执行</button>`
        : '';
      const logBtn = j.log_file
        ? `<button class="btn-job btn-log" id="jobLogBtn_${gIdx}" onclick="toggleJobLog(${gIdx})">📜 日志</button>`
        : '';
      const logBox = j.log_file
        ? `<div class="job-log collapsed" id="jobLog_${gIdx}"><div class="job-log-empty">点击「📜 日志」查看</div></div>`
        : '';
      const action = (runBtn || logBtn)
        ? `<div class="job-actions">${runBtn}${logBtn}</div>`
        : '';
      return `
        <div class="job-card ${j.system ? 'system' : ''}">
          <div class="job-head">
            <div class="job-name" title="点击修改名称" style="cursor:pointer;"
                 onclick="startEditJobName(${gIdx})">
              ${escapeHtml(j.custom_name || j.name)} ${badge}
            </div>
            <div class="job-sched">${j.schedule}</div>
          </div>
          <div class="job-desc">${j.desc}</div>
          <div class="job-cmd">${cmd}</div>
          ${action}
          ${logBox}
        </div>`;
    };

    const userJobs = jobs.map((j, i) => ({ j, i })).filter(o => !o.j.system);
    const sysJobs = jobs.map((j, i) => ({ j, i })).filter(o => o.j.system);

    userList.innerHTML = userJobs.length
      ? userJobs.map(o => renderCard(o.j, o.i)).join('')
      : '<div style="color:#71767b;font-size:13px;padding:10px 0;">无用户任务</div>';
    sysList.innerHTML = sysJobs.length
      ? sysJobs.map(o => renderCard(o.j, o.i)).join('')
      : '<div style="color:#71767b;font-size:13px;padding:10px 0;">无系统任务</div>';

  } catch(e) {
    console.error('加载状态失败:', e);
  }
}

// 按全量任务下标手动触发（支持微软积分 + img.ink）
async function runJobByIndex(idx) {
  if (isRunning) { alert('已有任务在执行中，请稍候…'); return; }
  const btn = document.getElementById('jobRun_' + idx);
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 执行中...'; }
  isRunning = true;
  try {
    const resp = await fetch('/api/run-job', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: idx })
    });
    const data = await resp.json();
    if (data.success) {
      // 展开该卡日志区并刷新内容
      const box = document.getElementById('jobLog_' + idx);
      if (box) { box.classList.remove('collapsed'); loadJobLog(idx); }
    } else {
      alert('❌ 执行失败：' + (data.error || '未知错误'));
    }
  } catch(e) {
    alert('请求失败: ' + e);
  } finally {
    isRunning = false;
    if (btn) { btn.disabled = false; btn.textContent = '▶ 立即执行'; }
  }
}

// 展开 / 收起某任务的独立日志区
async function toggleJobLog(idx) {
  const box = document.getElementById('jobLog_' + idx);
  if (!box) return;
  if (box.classList.contains('collapsed')) {
    box.classList.remove('collapsed');
    await loadJobLog(idx);
  } else {
    box.classList.add('collapsed');
  }
}

// 拉取某任务的独立日志
async function loadJobLog(idx) {
  const box = document.getElementById('jobLog_' + idx);
  if (!box) return;
  box.innerHTML = '<div class="job-log-empty">读取中…</div>';
  try {
    const resp = await fetch('/api/job-log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: idx })
    });
    const data = await resp.json();
    if (data.success && data.exists) {
      const esc = escapeHtml(data.log);
      box.innerHTML = '<pre class="job-log-pre">' + esc + '</pre>';
    } else {
      box.innerHTML = '<div class="job-log-empty">' + escapeHtml(data.log || '暂无日志') + '</div>';
    }
  } catch(e) {
    box.innerHTML = '<div class="job-log-empty">读取失败: ' + escapeHtml(e) + '</div>';
  }
}

// 折叠 / 展开系统任务区
function toggleSysJobs() {
  const list = document.getElementById('sysJobList');
  const toggle = document.getElementById('sysToggle');
  if (list.classList.contains('collapsed')) {
    list.classList.remove('collapsed');
    toggle.textContent = '▾ 收起';
  } else {
    list.classList.add('collapsed');
    toggle.textContent = '▸ 展开';
  }
}

// 卡片内「立即执行」按钮（旧入口，已被 runJobByIndex 取代）



async function toggleCron() {
  try {
    const resp = await fetch('/api/toggle-cron', { method: 'POST' });
    const data = await resp.json();
    if (data.success) {
      await loadStatus();
    } else {
      alert('操作失败：' + (data.error || '未知错误'));
    }
  } catch(e) {
    alert('请求失败: ' + e);
  }
}

// 重启面板：先拉起新进程再结束旧进程（零停机），下次请求即走新代码
async function restartPanel() {
  if (!confirm('确定重启面板？重启后新上传的 web_app.py 即生效。')) return;
  const btn = document.getElementById('btnRestart');
  btn.disabled = true; btn.textContent = '⏳ 重启中...';
  try {
    const resp = await fetch('/api/restart', { method: 'POST' });
    const data = await resp.json();
    if (data.success) {
      alert('✅ ' + (data.message || '重启中') + '\\n\\n即将自动刷新…');
      setTimeout(() => location.reload(), 3500);
    } else {
      alert('❌ 重启失败：' + (data.error || '未知错误'));
      btn.disabled = false; btn.textContent = '♻️ 重启面板';
    }
  } catch(e) {
    alert('请求失败: ' + e);
    btn.disabled = false; btn.textContent = '♻️ 重启面板';
  }
}


// 主题持久化（localStorage）：🌙 夜间 / ☀️ 日间
function applyTheme(mode) {
  const isLight = mode === 'light';
  document.body.classList.toggle('light', isLight);
  document.getElementById('fabTheme').textContent = isLight ? '☀️' : '🌙';
}

function toggleTheme() {
  const isLight = document.body.classList.contains('light');
  const next = isLight ? 'dark' : 'light';
  applyTheme(next);
  try { localStorage.setItem('panel_theme', next); } catch(e) {}
}

function goTop() {
  // 多重兜底，确保各浏览器/老内核都能回到顶部
  try { window.scrollTo(0, 0); } catch(e) {}
  try {
    const d = document.documentElement || document.body;
    d.scrollTop = 0;
    document.body.scrollTop = 0;
  } catch(e) {}
  // 立即隐藏回到顶部按钮，给出反馈
  const top = document.getElementById('fabTop');
  if (top) top.style.visibility = 'hidden';
}

// 悬浮按钮显隐：向下滚动隐藏，向上滚动出现（顶部附近仅隐藏「回到顶部」）
let lastScrollY = window.scrollY;
function onScroll() {
  const y = window.scrollY;
  const group = document.getElementById('fabGroup');
  if (!group) return;
  const top = document.getElementById('fabTop');
  if (y < 80) {
    // 顶部附近：显示整组，但「回到顶部」无意义则隐藏它
    group.classList.remove('hidden');
    if (top) top.style.visibility = (y < 10) ? 'hidden' : 'visible';
  } else if (y > lastScrollY + 4) {
    group.classList.add('hidden');           // 向下滚动：隐藏
  } else if (y < lastScrollY - 4) {
    group.classList.remove('hidden');        // 向上滚动：显示
    if (top) top.style.visibility = 'visible';
  }
  lastScrollY = y;
}

// Init
loadStatus();
// 初始化主题
try {
  const saved = localStorage.getItem('panel_theme') || 'dark';
  applyTheme(saved);
} catch(e) { applyTheme('dark'); }
// 注册滚动监听（控制悬浮按钮显隐）
window.addEventListener('scroll', onScroll, { passive: true });
onScroll();
// Auto refresh every 60 seconds
pollingTimer = setInterval(loadStatus, 60000);
// Update clock every second
setInterval(() => {
  document.getElementById('currentTime').textContent = fmtTime(Date.now());
}, 1000);
</script>
</body>
</html>"""

# ------------------------------------------------------------
# 读取全部 cron 任务（只读展示用）
# ------------------------------------------------------------
def get_all_cron_jobs():
    """读取系统 crontab，返回任务列表（dict: schedule, command, is_imgink）"""
    raw = ""
    # 优先直接读 QNAP 的 crontab 文件（所有用户可读，避免 crontab -l 的 suid 限制）
    for path in ("/etc/config/crontab", "/var/spool/cron/crontabs/root"):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    raw = f.read()
            except Exception:
                pass
            if raw:
                break
    # 兜底：尝试 crontab -l（root 身份运行时）
    if not raw:
        try:
            r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                raw = r.stdout
        except Exception:
            pass

    # 已知任务的「中文名 + 说明」映射（按命令关键字匹配）
    KNOWN = [
        {
            "keys": ["sign_expand.py"],
            "name": "🖼️ img.ink 自动扩容",
            "desc": "每天 07:00 自动调用图床扩容脚本，为 img.ink 账户增加存储空间。可在面板点击「立即执行」手动触发（跳过随机延迟）。",
            "runnable": True,
            "imgink": True,
            "system": False,
            "log": os.path.join(BASE_DIR, "cron.log"),
        },
        {
            "keys": ["start_web.sh"],
            "name": "🔄 Web 面板保活",
            "desc": "每 5 分钟检测一次 Web 面板进程，若异常退出则自动重启，保证管理界面 24 小时可用。属后台守护任务，不建议手动执行。",
            "runnable": False,
            "imgink": False,
            "system": True,
            "log": None,
        },
        {
            # 注意：保活任务必须排在「微软积分」之前，否则会被 microsoft/ 关键字误匹配
            "keys": ["nas_keepalive.sh", "--keepalive"],
            "name": "🔐 微软登录态保活",
            "desc": "每 18 天凌晨 3:30 触发，仅验证登录态并访问几个已登录页面（不跑搜索任务），顺延微软会话有效期、回写 storage_state.json，降低因 cookie 过期而需在 Windows 手动重新登录（过 2FA）的频率。点击「立即执行」可手动触发一次保活。",
            "runnable": True,
            "imgink": False,
            "system": False,
            "log": "/share/CACHEDEV1_DATA/Web/gadget/microsoft/keepalive.log",
        },
        {
            "keys": ["nas_cron.sh", "nas_main.py", "microsoft/"],
            "name": "🪟 微软积分自动获取",
            "desc": "每天 09:00 与 21:00 触发，脚本内部再随机延迟 0~30 分钟启动；自动完成必应 PC/移动端搜索、每日卡片与「每日连续打卡活动」等打卡任务攒微软积分。点击「立即执行」可手动触发（后台运行、随机延迟控制在 1 分钟内，约 15~25 分钟完成）。",
            "runnable": True,
            "imgink": False,
            "system": False,
            "log": "/share/CACHEDEV1_DATA/Web/gadget/microsoft/nas.log",
        },
    ]

    def match_known(cmd):
        for k in KNOWN:
            if any(key in cmd for key in k["keys"]):
                return k
        return None

    jobs = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        # cron 格式：m h dom mon dow cmd...  前 5 段是时间
        if len(parts) < 6:
            continue
        schedule = " ".join(parts[:5])
        command = " ".join(parts[5:])
        known = match_known(command)
        custom_names = get_job_names()
        custom_name = custom_names.get(command)
        if known:
            jobs.append({
                "schedule": schedule,
                "command": command,
                "is_imgink": known.get("imgink", False),
                "system": known.get("system", False),
                "name": known["name"],
                "desc": known["desc"],
                "runnable": known["runnable"],
                "log_file": known.get("log"),
                "custom_name": custom_name,
            })
        else:
            # 其余视为 QNAP 系统任务（只读展示，不可手动触发）
            jobs.append({
                "schedule": schedule,
                "command": command,
                "is_imgink": False,
                "system": True,
                "name": "⚙️ 系统任务",
                "desc": "QNAP 系统自带定时任务（系统更新 / 应用检查等），由系统自动管理，无需手动干预。",
                "runnable": False,
                "log_file": None,
                "custom_name": custom_name,
            })
    return jobs


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@app.route('/')
def index():
    return render_template_string(TEMPLATE, title=get_panel_title())


@app.route('/api/status')
def api_status():
    """返回当前状态"""
    cron_active = not os.path.exists(DISABLED_FLAG)
    cron_detail = "每天 07:00" if cron_active else "已暂停"

    return jsonify({
        'cron_active': cron_active,
        'cron_detail': cron_detail,
        'cron_jobs': get_all_cron_jobs(),
        'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


@app.route('/api/get-title')
def api_get_title():
    """返回当前面板标题"""
    return jsonify({'success': True, 'title': get_panel_title()})


@app.route('/api/set-title', methods=['POST'])
def api_set_title():
    """保存新的面板标题（持久化到 title.txt，重启后仍生效）"""
    try:
        payload = request.get_json(silent=True) or {}
        new_title = (payload.get('title') or '').strip()
        if not new_title:
            return jsonify({'success': False, 'error': '标题不能为空'})
        set_panel_title(new_title)
        return jsonify({'success': True, 'title': new_title})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/set-job-name', methods=['POST'])
def api_set_job_name():
    """保存某条 cron 任务的自定义名称（按 command 唯一标识，持久化到 jobnames.json）"""
    try:
        payload = request.get_json(silent=True) or {}
        command = (payload.get('command') or '').strip()
        name = (payload.get('name') or '').strip()
        if not command:
            return jsonify({'success': False, 'error': '缺少命令标识'})
        set_job_name(command, name)
        return jsonify({'success': True, 'name': name or None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/job-log', methods=['POST'])
def api_job_log():
    """按任务下标返回该任务独立的运行日志"""
    try:
        payload = request.get_json(silent=True) or {}
        idx = int(payload.get('index', -1))
        jobs = get_all_cron_jobs()
        if idx < 0 or idx >= len(jobs):
            return jsonify({'success': False, 'error': '无效的任务索引'})
        log_file = jobs[idx].get('log_file')
        if not log_file or not os.path.exists(log_file):
            return jsonify({'success': True, 'log': '(暂无日志)', 'exists': False})
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()[-200:]
        return jsonify({'success': True, 'log': ''.join(lines), 'exists': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/run', methods=['POST'])
def api_run():
    """手动触发签到"""
    try:
        python = "/share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/python3"
        child_env = {
            **os.environ,
            'PYTHONUNBUFFERED': '1',
            'MANUAL': '1',
            'PYTHONPATH': '/share/homes/Mars/.local/lib/python3.12/site-packages',
        }
        result = subprocess.run(
            [python, SCRIPT_PATH],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=300,
            env=child_env
        )
        output = result.stdout + result.stderr
        return jsonify({
            'success': True,
            'result': output.strip() or '执行完毕（无输出）',
            'exit_code': result.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': '执行超时（超过2分钟）'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/check-expand', methods=['POST'])
def api_check_expand():
    """只读自检：判断今日 img.ink 扩容是否真的完成（不重复触发扩容）。"""
    try:
        # 解释器：NAS 上用固定路径；其他环境回退到当前面板进程的解释器
        python = "/share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/python3"
        if not os.path.exists(python):
            python = sys.executable
        child_env = {**os.environ, 'PYTHONUNBUFFERED': '1'}
        if os.path.exists("/share/homes/Mars/.local/lib/python3.12/site-packages"):
            child_env['PYTHONPATH'] = "/share/homes/Mars/.local/lib/python3.12/site-packages"
        result = subprocess.run(
            [python, SCRIPT_PATH, "--check"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env=child_env
        )
        output = result.stdout + result.stderr
        return jsonify({
            'success': True,
            'result': output.strip() or '自检完毕（无输出）',
            'exit_code': result.returncode,
            'ok': result.returncode == 0,
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': '执行超时（超过2分钟）'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/run-job', methods=['POST'])
def api_run_job():
    """按 crontab 行索引手动触发某个已登记的可执行任务"""
    try:
        payload = request.get_json(silent=True) or {}
        idx = int(payload.get('index', -1))
        jobs = get_all_cron_jobs()
        if idx < 0 or idx >= len(jobs):
            return jsonify({'success': False, 'error': '无效的任务索引'})
        job = jobs[idx]
        if not job.get('runnable'):
            return jsonify({'success': False, 'error': '该任务不可手动执行'})

        command = job['command']
        env = {**os.environ}

        # 微软相关任务（每日积分 / 登录态保活）：直接执行 crontab 中的命令
        if any(k in command for k in ("nas_keepalive.sh", "--keepalive",
                                      "nas_cron.sh", "nas_main.py", "microsoft/")):
            is_keepalive = ("nas_keepalive.sh" in command) or ("--keepalive" in command)
            script = command
            # 若是完整 crontab 行（含时间字段），取最后的命令部分
            parts = command.split()
            if len(parts) >= 6 and all(x.replace('*', '').isdigit() or x in ('*',)
                                       for x in parts[:5]):
                script = " ".join(parts[5:])
            # 手动触发：注入 IMMEDIATE=1，让 nas_cron.sh 的随机延迟控制在 1 分钟内；
            # 并用 Popen 后台启动（start_new_session），面板立即返回、不再等待任务结束，
            # 彻底消除「超时 10 分钟」误报（任务本身会跑 15~25 分钟，日志写入 nas.log）。
            env = {**os.environ, 'IMMEDIATE': '1'}
            subprocess.Popen(
                ["/bin/sh", "-c", script],
                cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=env, start_new_session=True,
            )
            default_msg = ('已在后台触发微软登录态保活（约 5 分钟，请稍后查看保活日志）'
                           if is_keepalive else
                           '已在后台触发微软积分任务（随机延迟控制在 1 分钟内，约 15~25 分钟完成，'
                           '请稍后点「📜 日志」查看 nas.log）')
            return jsonify({
                'success': True,
                'result': default_msg,
                'exit_code': None,
                'background': True,
            })

        # img.ink 扩容任务：直接调脚本（跳过随机延迟）
        if any(k in command for k in ("sign_expand.py", "auto_sign/sign_expand")):
            python = "/share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/python3"
            child_env = {
                **env,
                'PYTHONUNBUFFERED': '1',
                'MANUAL': '1',
                'PYTHONPATH': '/share/homes/Mars/.local/lib/python3.12/site-packages',
            }
            result = subprocess.run(
                [python, SCRIPT_PATH], cwd=BASE_DIR, capture_output=True,
                text=True, timeout=300, env=child_env
            )
            output = result.stdout + result.stderr
            return jsonify({
                'success': True,
                'result': output.strip() or '执行完毕（无输出）',
                'exit_code': result.returncode,
            })

        return jsonify({'success': False, 'error': '未知的可执行任务类型'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': '执行超时（超过10分钟）'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/toggle-cron', methods=['POST'])
def api_toggle_cron():
    """切换计划任务启用/禁用"""
    try:
        if os.path.exists(DISABLED_FLAG):
            os.remove(DISABLED_FLAG)
            return jsonify({'success': True, 'enabled': True, 'message': '计划任务已启用'})
        else:
            with open(DISABLED_FLAG, 'w') as f:
                f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            return jsonify({'success': True, 'enabled': False, 'message': '计划任务已暂停'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/restart', methods=['POST'])
def api_restart():
    """重启 Web 面板（直接拉起新进程，不依赖 start_web.sh 的保活判断）。

    旧逻辑用 start_web.sh 做保活判断，但存在竞态：延迟拉起期间旧进程还在，
    start_web.sh 判断「进程已存在」就不拉新进程，导致重启失效。
    新逻辑：先杀掉所有 web_app.py 进程，再用 setsid 直接拉起当前文件自身，
    确保新进程一定加载磁盘上的最新代码。
    """
    try:
        python = "/share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/python3"
        script = os.path.join(BASE_DIR, "web_app.py")
        env = {**os.environ, 'PYTHONPATH': '/share/homes/Mars/.local/lib/python3.12/site-packages'}

        # 1) 在后台独立 shell 中：先杀旧进程，再 setsid 拉起（彻底解耦，避免自杀中断拉起）
        restart_cmd = (
            f"sleep 1; "
            f"ps aux | grep '[w]eb_app.py' | awk '{{print $2}}' | xargs -r kill; "
            f"sleep 1; "
            f"setsid {python} {script} >> {os.path.join(BASE_DIR, 'web.log')} 2>&1 &"
        )
        subprocess.Popen(
            ["/bin/sh", "-c", restart_cmd],
            cwd=BASE_DIR, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return jsonify({'success': True, 'message': '面板正在重启，约 4 秒后生效，将自动刷新页面'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
if __name__ == '__main__':
    print("=" * 50)
    print("img.ink 自动扩容 - Web 管理面板")
    print("=" * 50)
    print(f"访问地址: http://<NAS_IP>:9999")
    print(f"例如:     http://192.168.5.4:9999")
    print(f"按 Ctrl+C 停止服务")
    print("=" * 50)
    app.run(host='0.0.0.0', port=9999, debug=False)
