# ============================================================
# deploy.ps1  —  本地 web_app.py -> QNAP NAS，并重启面板
# 策略：sftp 批处理上传（QNAP 无 scp 子系统，但 sftp 可用）
#        + 远端独立 shell 脚本执行重启
# ============================================================

$NAS_HOST   = "192.168.5.4"
$NAS_PORT   = "23023"
$NAS_USER   = "Mars"
$REMOTE_DIR = "/share/CACHEDEV1_DATA/Web/gadget/auto_sign"

$LOCAL_FILE  = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "web_app.py"
$REMOTE_FILE = $REMOTE_DIR + "/web_app.py"
$REMOTE_RST  = $REMOTE_DIR + "/deploy_restart.sh"

if (-not (Test-Path $LOCAL_FILE)) {
    Write-Error ("未找到本地文件: " + $LOCAL_FILE)
    exit 1
}

$target = $NAS_USER + "@" + $NAS_HOST
$SSH_OPT = "-p $NAS_PORT -o StrictHostKeyChecking=no -o BatchMode=no"

# ---------- 上传函数（sftp 批处理）----------
function Send-File {
    param($LocalPath, $RemotePath)
    $dir = Split-Path -Parent $RemotePath
    $batch = Join-Path $env:TEMP ("sftp_" + [Guid]::NewGuid().ToString("N") + ".txt")
    # 用 - 引用本地路径中的空格；远程先 mkdir -p
    $lines = @()
    $lines += ("mkdir ""$dir""")
    $lines += ("put ""$LocalPath"" ""$RemotePath""")
    $lines += "bye"
    Set-Content -Encoding ASCII $batch ($lines -join "`n")
    sftp -P $NAS_PORT -o StrictHostKeyChecking=no $target < $batch
    $code = $LASTEXITCODE
    Remove-Item $batch -ErrorAction SilentlyContinue
    return $code
}

# ---------- [1/3] 上传 web_app.py ----------
Write-Host "`n[1/3] 上传 web_app.py ..." -ForegroundColor Cyan
$r = Send-File -LocalPath $LOCAL_FILE -RemotePath $REMOTE_FILE
if ($r -ne 0) { Write-Error "上传 web_app.py 失败"; exit 1 }
Write-Host "      完成。" -ForegroundColor Green

# ---------- [2/3] 上传重启脚本 ----------
Write-Host "`n[2/3] 上传重启脚本 ..." -ForegroundColor Cyan
$restartSh = "#!/bin/sh" + [Environment]::NewLine `
  + "DIR=""/share/CACHEDEV1_DATA/Web/gadget/auto_sign""" + [Environment]::NewLine `
  + "PID=`$(ps aux | grep ""[w]eb_app.py"" | awk '{print `$2}')" + [Environment]::NewLine `
  + "if [ -n ""`$PID"" ]; then" + [Environment]::NewLine `
  + "  echo ""kill old pid: `$PID""" + [Environment]::NewLine `
  + "  kill `$PID 2>/dev/null" + [Environment]::NewLine `
  + "fi" + [Environment]::NewLine `
  + "sleep 2" + [Environment]::NewLine `
  + "/bin/sh ""`$DIR/start_web.sh""" + [Environment]::NewLine `
  + "sleep 2" + [Environment]::NewLine `
  + "HIT=`$(curl -s http://127.0.0.1:9999/api/status | grep -o '""name""' | head -1)" + [Environment]::NewLine `
  + "if [ -n ""`$HIT"" ]; then" + [Environment]::NewLine `
  + "  echo ""DEPLOY_OK: 新版本已生效 (含 name 字段)""" + [Environment]::NewLine `
  + "else" + [Environment]::NewLine `
  + "  echo ""DEPLOY_WARN: 未检测到 name 字段，请手动检查""" + [Environment]::NewLine `
  + "fi"
$tmpR = Join-Path $env:TEMP ("restart_" + [Guid]::NewGuid().ToString("N") + ".sh")
Set-Content -NoNewline -Encoding ASCII $tmpR $restartSh
$r = Send-File -LocalPath $tmpR -RemotePath $REMOTE_RST
Remove-Item $tmpR -ErrorAction SilentlyContinue
if ($r -ne 0) { Write-Error "上传重启脚本失败"; exit 1 }
Write-Host "      完成。" -ForegroundColor Green

# ---------- [3/3] 执行重启 ----------
Write-Host "`n[3/3] 执行重启 ..." -ForegroundColor Cyan
ssh -tt -p $NAS_PORT -o StrictHostKeyChecking=no $target ("sh " + $REMOTE_RST)

Write-Host "`n完成。浏览器打开 http://${NAS_HOST}:9999/ 并按 Ctrl+F5 强制刷新。" -ForegroundColor Green
