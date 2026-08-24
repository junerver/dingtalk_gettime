# start.ps1
# 干净启动 dingtalk-gettime 守护进程：
#   1. 先释放被旧进程占用的 8345 端口（避免 PM2 启动即崩溃、反复重启）
#   2. 删除已有的 PM2 实例（若存在）
#   3. 用 pythonw 无窗口后台启动
#
# 用法（PowerShell，在项目根目录）：
#   .\start.ps1

$ErrorActionPreference = 'SilentlyContinue'

Write-Host "[1/3] 清理占用端口 8345 的旧进程..."
$ownerPids = Get-NetTCPConnection -LocalPort 8345 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

if (-not $ownerPids) {
    Write-Host "  端口 8345 当前无人占用。"
} else {
    foreach ($pidv in $ownerPids) {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$pidv"
        $cmd = if ($p) { $p.CommandLine } else { "" }
        if ($cmd -match 'dingtalk_gettime|main\.py') {
            Write-Host "  终止本项目的旧进程 PID=$pidv : $cmd"
            Stop-Process -Id $pidv -Force
        } else {
            Write-Host "  端口被非本项目进程占用(PID=$pidv)，为安全起见跳过: $cmd"
            Write-Host "  如需强制释放，请手动结束该进程后再运行本脚本。"
        }
    }
}

Write-Host "[2/3] 移除已有的 PM2 实例（若存在）..."
pm2 delete dingtalk-gettime 2>$null

Write-Host "[3/3] 以无窗口模式启动守护进程（pythonw）..."
pm2 startOrRestart .\ecosystem.config.js
pm2 save

Write-Host ""
Write-Host "完成。查看日志： pm2 logs dingtalk-gettime"
Write-Host "查看状态：     pm2 status"
