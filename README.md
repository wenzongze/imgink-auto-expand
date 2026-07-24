# img.ink 图床自动扩容 + Web 管理面板

> **关于本项目**
> - 支持在 **NAS 上部署并每天自动运行**，可独立建立**图形化页面**查看与管理定时任务。
> - 目前**仅限 img.ink** 图床平台。
> - 本项目**由 AI 辅助编写**（代码生成、改 bug、文档整理均在 AI 协助下完成）。
> - 开源协议：**MIT License**（详见仓库内 `LICENSE` 文件）。可自由使用、复制、修改、再分发，
>   包括商业用途，但**需保留版权与许可声明**，且不提供任何担保。
> - 如遇 BUG，欢迎在仓库留言反馈，或自行用 AI 修复后提交。

一个运行在 **QNAP NAS**（或任意有 Python3 的 Linux 设备）上的小工具：

- 每天自动为 [img.ink](https://img.ink) 图床账户**免费扩容一次**存储空间
- 配套 **Flask 图形化面板**（端口 9999），可查看状态、手动执行、暂停/启停、看日志、改标题、改任务名
- 支持**邮件通知**（QQ 邮箱 SMTP）
- 内置「页面自检」按钮，改完代码可一键确认是否生效

---

## 功能特性

| 功能 | 说明 |
|------|------|
| 自动扩容 | 每天定时登录 + 扩容，内置随机延迟模拟真人 |
| Web 面板 | 浏览器访问，无需命令行 |
| 手动执行 | 面板点「立即执行」可跳过延迟立即跑 |
| 标题/任务名自定义 | 点击面板标题或任务名即可改名，持久化保存 |
| 暂停/启用 | 一键暂停所有计划任务 |
| 日志查看 | 面板内直接看各任务最近 200 行日志 |
| 页面自检 | 一键检测样式/接口是否生效，避免浏览器缓存困扰 |
| 日间/夜间模式 | 右下角悬浮按钮切换 |
| 保活重启 | 面板「♻️ 重启面板」按钮，先杀旧进程再拉新进程 |

---

## 目录结构

```
.
├── web_app.py              # Flask 图形化面板（端口 9999）
├── sign_expand.py          # 核心扩容脚本
├── notify.py               # 邮件通知模块
├── start_web.sh            # 面板保活 + 开机自启脚本
├── requirements.txt        # Python 依赖
├── config.example.ini      # 配置模板（复制为 config.ini 后填写）
├── 部署与图形化操作指南.md  # 详细部署与使用文档
└── .gitignore              # 忽略隐私/运行时文件
```

> ⚠️ 首次使用请把 `config.example.ini` 复制为 `config.ini` 并填入你的账号。

---

## 快速开始

### 1. 准备 Python3 环境

需要 Python 3.8+，并安装依赖：

```bash
pip3 install -r requirements.txt
```

> QNAP 用户：用 Python3 QPKG 自带的 python3，例如
> `/share/CACHEDEV1_DATA/.qpkg/Python3/opt/python3/bin/python3 -m pip install --user requests flask`

### 2. 配置账号

```bash
cp config.example.ini config.ini
# 编辑 config.ini，填入 img.ink 账号、QQ 邮箱与授权码
```

### 3. 启动面板

```bash
python3 web_app.py
# 或以后台保活方式（推荐）：
# /bin/sh start_web.sh
```

浏览器打开 `http://<你的设备IP>:9999` 即可。

### 4. 配置定时任务（可选）

把 `sign_expand.py` 加入 crontab，例如每天 07:00 触发（脚本内部会再随机延迟到设定时段）：

```
0 7 * * * /usr/bin/python3 /路径/web_app.py所在目录/sign_expand.py >> /路径/cron.log 2>&1
```

---

## 详细说明

完整部署步骤、面板每一项操作、常见问题排查，见 **[部署与图形化操作指南.md](部署与图形化操作指南.md)**。

---

## 安全提示

- `config.ini` 含账号密码，**请勿提交到公开仓库**（已写入 `.gitignore`）。
- 面板自身无鉴权，建议仅在信任的内网环境暴露 9999 端口。
- 如需公网访问，请自行加反代 + 鉴权（如 Nginx + Basic Auth / 隧道服务）。

---

## 更新与维护

如何把代码改动推送到 Gitee / GitHub 双平台、同步到 NAS 运行环境、以及访问地址说明，见 **[更新与维护.md](更新与维护.md)**。
