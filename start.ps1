#Requires -Version 5.1
<#
.SYNOPSIS
    构建策略配置系统：一键启动 / 停止前后端开发服务（Windows PowerShell 5.1+）。
.DESCRIPTION
    一条命令同时启动后端 Django（默认 http://localhost:8000，API 前缀 /api）
    与前端 Vite（默认 http://localhost:8848），端口就绪后自动打开浏览器。

    - 服务以后台进程运行，控制台输出重定向到根目录 logs/ 下的日志文件；
    - 首次运行且 backend/.env 缺失时，自动从 .env.example 生成并执行
      scripts/prestart.ps1（makemigrations + migrate + seed）；
    - 非首次启动会静默应用已提交但未应用的迁移（migrate），并检查是否有
      模型变更尚未生成迁移文件（makemigrations --check）——按 AGENTS.md 约定，
      迁移文件必须先生成并提交，不允许带病启动；
    - 停止时读取 logs/*.pid 按进程树结束；PID 记录缺失或失效但端口仍被
      占用时，按端口兜底结束并给出提示；
    - 前端通过命令行参数覆盖端口（--port），与 -FrontendPort 保持一致。

.PARAMETER Stop
    停止前后端服务后退出（不启动）。
.PARAMETER Restart
    先停止再启动。
.PARAMETER Status
    仅查看前后端服务运行状态后退出。
.PARAMETER NoBrowser
    启动成功后不自动打开浏览器。
.PARAMETER BackendPort
    后端端口，默认 8000。
.PARAMETER FrontendPort
    前端端口，默认 8848。

.EXAMPLE
    .\start.ps1
    一键启动前后端并打开浏览器。
.EXAMPLE
    .\start.ps1 -Stop
    停止前后端服务。
.EXAMPLE
    .\start.ps1 -Status
    查看服务运行状态。
.EXAMPLE
    .\start.ps1 -Restart -NoBrowser
    重启前后端，不打开浏览器。
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Status,
    [switch]$NoBrowser,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 8848
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

trap {
    Write-Host "  [脚本异常] $_" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
$Root = $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$LogDir = Join-Path $Root "logs"
$BackendPidFile = Join-Path $LogDir "backend.pid"
$FrontendPidFile = Join-Path $LogDir "frontend.pid"
$BackendLog = Join-Path $LogDir "backend.log"
$BackendErrLog = Join-Path $LogDir "backend.err.log"
$FrontendLog = Join-Path $LogDir "frontend.log"
$FrontendErrLog = Join-Path $LogDir "frontend.err.log"

# ---------------------------------------------------------------------------
# 输出辅助
# ---------------------------------------------------------------------------
function Write-Info { param([string]$Message) Write-Host "  $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "  $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "  $Message" -ForegroundColor Yellow }
function Write-Err { param([string]$Message) Write-Host "  $Message" -ForegroundColor Red }

function Write-Title {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Magenta
}

# ---------------------------------------------------------------------------
# 端口工具
# ---------------------------------------------------------------------------
function Get-PortOwnerPids {
    param([int]$Port)
    $owners = @()
    try {
        $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    }
    catch {
        $owners = @()
    }
    # 过滤空值；必须用 -NoEnumerate 原样返回数组——直接 return 空数组会被管道折叠成 $null，
    # StrictMode 下调用方 $null.Count 直接抛异常（2026-10-12 冒烟测试实测）
    $owners = @($owners | Where-Object { $_ -ne $null })
    Write-Output -NoEnumerate $owners
}

function Test-PortListening {
    param([int]$Port)
    return (Get-PortOwnerPids -Port $Port).Count -gt 0
}

function Wait-PortReady {
    param([int]$Port, [int]$TimeoutSec, [string]$Name)
    for ($elapsed = 1; $elapsed -le $TimeoutSec; $elapsed++) {
        if (Test-PortListening -Port $Port) {
            Write-Ok "$Name 已就绪：端口 $Port（等待 ${elapsed}s）"
            return $true
        }
        if ($elapsed % 10 -eq 0) {
            Write-Info "$Name 启动中（已等待 ${elapsed}s）..."
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

# ---------------------------------------------------------------------------
# 停止服务：PID 进程树优先，端口占用兜底
# ---------------------------------------------------------------------------
function Stop-ServiceByName {
    param([string]$Name, [string]$PidFile, [int]$Port)
    $killed = $false
    if (Test-Path -LiteralPath $PidFile) {
        $recordedPid = (Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue)
        if ($recordedPid) { $recordedPid = $recordedPid.Trim() }
        if ($recordedPid -match "^\d+$") {
            $proc = Get-Process -Id ([int]$recordedPid) -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Info "停止 $Name（PID $recordedPid，含子进程树）..."
                & taskkill /PID $recordedPid /T /F > $null 2>&1
                $killed = $true
            }
        }
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
    foreach ($ownerPid in (Get-PortOwnerPids -Port $Port)) {
        $owner = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        if ($owner) {
            Write-Warn "$Name 端口 $Port 仍被 PID $ownerPid（$($owner.ProcessName)）占用（PID 记录缺失或已失效），按进程树兜底结束"
            & taskkill /PID $ownerPid /T /F > $null 2>&1
            $killed = $true
        }
    }
    if ($killed) {
        Write-Ok "$Name 已停止"
    }
    else {
        Write-Info "$Name 未在运行"
    }
    return $killed
}

# ---------------------------------------------------------------------------
# 后端环境初始化：首次建库 + 种子数据；常规启动应用迁移并检查迁移文件
# ---------------------------------------------------------------------------
function Initialize-BackendEnv {
    param([switch]$FirstTime)
    if ($FirstTime) {
        Write-Info "执行首次初始化（makemigrations + migrate + seed）..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $BackendDir "scripts\prestart.ps1")
        if ($LASTEXITCODE -ne 0) {
            Write-Err "首次初始化失败，请根据上方输出排查后重试"
            return $false
        }
        Write-Ok "首次初始化完成"
        return $true
    }
    Push-Location $BackendDir
    try {
        # 应用已提交但未应用的迁移（幂等；无待应用迁移时约 1-2 秒返回）
        & python manage.py migrate --noinput > $null 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "migrate 执行失败，请手动在 backend 目录执行 python manage.py migrate 排查"
        }
        # 检查模型变更是否已生成迁移（按约定必须生成并提交，禁止带病启动）
        & python manage.py makemigrations --check --dry-run > $null 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "检测到模型变更尚未生成迁移文件：请在 backend 目录执行 makemigrations 并提交（AGENTS.md 约定）"
        }
    }
    finally {
        Pop-Location
    }
    return $true
}

# ---------------------------------------------------------------------------
# 启动后端 / 前端
# ---------------------------------------------------------------------------
# 日志目标登记表：键为服务名，值为人类可读的日志位置说明（重定向文件或最小化窗口）
$script:LogTargets = @{}

# 以后台进程方式启动服务，并登记 PID：
# 优先用 -RedirectStandard* 把控制台输出落盘（隐藏窗口）；
# 部分环境的 PowerShell 5.1 对该参数有已知缺陷——进程创建前即抛「字典关键字 Path/path 冲突」，
# 此时降级为最小化控制台窗口，实时输出点击任务栏对应窗口即可查看（2026-10-12 实测）。
function Start-DetachedService {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$PidFile,
        [string]$LogFile,
        [string]$ErrLogFile
    )
    try {
        $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory `
            -RedirectStandardOutput $LogFile -RedirectStandardError $ErrLogFile -PassThru -WindowStyle Hidden
        $script:LogTargets[$Name] = "日志文件：$LogFile"
    }
    catch {
        Write-Warn "$Name 输出重定向不可用（$($_.Exception.Message)），降级为最小化窗口模式，实时输出请点击任务栏对应窗口"
        $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory `
            -PassThru -WindowStyle Minimized
        $script:LogTargets[$Name] = "最小化窗口（实时输出）"
    }
    $proc.Id | Set-Content -LiteralPath $PidFile -Encoding Ascii
    Write-Info "$Name 启动中（PID $($proc.Id)）..."
    return $proc
}

function Start-BackendService {
    $owners = Get-PortOwnerPids -Port $BackendPort
    if ($owners.Count -gt 0) {
        $recordedPid = $null
        if (Test-Path -LiteralPath $BackendPidFile) {
            $rawPid = Get-Content -LiteralPath $BackendPidFile -Raw -ErrorAction SilentlyContinue
            if ($rawPid) { $recordedPid = $rawPid.Trim() }
        }
        $recordedAlive = $false
        if ($recordedPid -and $recordedPid -match "^\d+$") {
            $recordedAlive = [bool](Get-Process -Id ([int]$recordedPid) -ErrorAction SilentlyContinue)
        }
        if ($recordedAlive) {
            Write-Ok "后端 Django 已在运行（启动 PID $recordedPid，端口 $BackendPort 监听中），跳过重复启动"
            return $true
        }
        Write-Warn "后端端口 $BackendPort 被其他进程占用（PID: $($owners -join ', ')），跳过启动；如为本项目残留进程，请先执行 .\start.ps1 -Stop"
        return $false
    }
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        Write-Err "未找到 python：请先安装 Python 3.11+ 并确认已在 PATH 中"
        return $false
    }
    $proc = Start-DetachedService -Name "后端 Django" -FilePath $pythonCmd.Source `
        -ArgumentList "manage.py", "runserver", "$BackendPort" `
        -WorkingDirectory $BackendDir -PidFile $BackendPidFile -LogFile $BackendLog -ErrLogFile $BackendErrLog
    if (Wait-PortReady -Port $BackendPort -TimeoutSec 90 -Name "后端 Django") {
        return $true
    }
    Write-Err "后端 90 秒内未就绪，请查看日志：$BackendLog"
    return $false
}

function Start-FrontendService {
    $owners = Get-PortOwnerPids -Port $FrontendPort
    if ($owners.Count -gt 0) {
        $recordedPid = $null
        if (Test-Path -LiteralPath $FrontendPidFile) {
            $rawPid = Get-Content -LiteralPath $FrontendPidFile -Raw -ErrorAction SilentlyContinue
            if ($rawPid) { $recordedPid = $rawPid.Trim() }
        }
        $recordedAlive = $false
        if ($recordedPid -and $recordedPid -match "^\d+$") {
            $recordedAlive = [bool](Get-Process -Id ([int]$recordedPid) -ErrorAction SilentlyContinue)
        }
        if ($recordedAlive) {
            Write-Ok "前端 Vite 已在运行（启动 PID $recordedPid，端口 $FrontendPort 监听中），跳过重复启动"
            return $true
        }
        Write-Warn "前端端口 $FrontendPort 被其他进程占用（PID: $($owners -join ', ')），跳过启动；如为本项目残留进程，请先执行 .\start.ps1 -Stop"
        return $false
    }
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCmd) {
        Write-Err "未找到 node：请先安装 Node.js（20.19+ 或 22.13+）并确认已在 PATH 中"
        return $false
    }
    # 优先解析 npm.cmd（标准 Node 安装形态）；部分环境 npm 会解析到 .ps1 shim，不能直接作为进程启动
    $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCmd) { $npmCmd = Get-Command npm -ErrorAction SilentlyContinue }
    if (-not $npmCmd) {
        Write-Err "未找到 npm：请先安装 Node.js（20.19+ 或 22.13+）并确认已在 PATH 中"
        return $false
    }
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules"))) {
        Write-Info "未检测到 node_modules，执行 npm ci（首次依赖安装，可能需要几分钟）..."
        Push-Location $FrontendDir
        try {
            & $npmCmd.Source ci
            if ($LASTEXITCODE -ne 0) {
                Write-Err "npm ci 失败，请手动在 frontend 目录执行 npm ci 后重试"
                return $false
            }
        }
        finally {
            Pop-Location
        }
    }
    $proc = Start-DetachedService -Name "前端 Vite" -FilePath $npmCmd.Source `
        -ArgumentList "run", "dev", "--", "--port", "$FrontendPort" `
        -WorkingDirectory $FrontendDir -PidFile $FrontendPidFile -LogFile $FrontendLog -ErrLogFile $FrontendErrLog
    if (Wait-PortReady -Port $FrontendPort -TimeoutSec 120 -Name "前端 Vite") {
        return $true
    }
    Write-Err "前端 120 秒内未就绪，请查看日志：$FrontendLog"
    return $false
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
if ($BackendPort -lt 1 -or $BackendPort -gt 65535 -or $FrontendPort -lt 1 -or $FrontendPort -gt 65535) {
    Write-Err "端口必须在 1-65535 之间（当前：后端 $BackendPort，前端 $FrontendPort）"
    exit 1
}

if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

Write-Title "构建策略配置系统 · 开发服务一键脚本（根目录 start.ps1）"

if ($Status) {
    $backendPid = "-"
    if (Test-Path -LiteralPath $BackendPidFile) {
        $rawPid = Get-Content -LiteralPath $BackendPidFile -Raw -ErrorAction SilentlyContinue
        if ($rawPid) { $backendPid = $rawPid.Trim() }
    }
    $frontendPid = "-"
    if (Test-Path -LiteralPath $FrontendPidFile) {
        $rawPid = Get-Content -LiteralPath $FrontendPidFile -Raw -ErrorAction SilentlyContinue
        if ($rawPid) { $frontendPid = $rawPid.Trim() }
    }
    @(
        [pscustomobject]@{
            服务 = "后端 API（Django）"
            地址 = "http://localhost:$BackendPort/api"
            状态 = $(if (Test-PortListening -Port $BackendPort) { "运行中" } else { "未运行" })
            PID = $backendPid
        },
        [pscustomobject]@{
            服务 = "前端页面（Vite）"
            地址 = "http://localhost:$FrontendPort"
            状态 = $(if (Test-PortListening -Port $FrontendPort) { "运行中" } else { "未运行" })
            PID = $frontendPid
        }
    ) | Format-Table -AutoSize
    exit 0
}

if ($Stop -or $Restart) {
    Write-Title "停止服务"
    $null = Stop-ServiceByName -Name "后端 Django" -PidFile $BackendPidFile -Port $BackendPort
    $null = Stop-ServiceByName -Name "前端 Vite" -PidFile $FrontendPidFile -Port $FrontendPort
}

if ($Stop) {
    Write-Host ""
    Write-Ok "已停止。日志保留在 $LogDir，排查问题后可手动删除"
    exit 0
}

Write-Title "启动前检查"
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Err "未找到 python：请先安装 Python 3.11+ 并确认已在 PATH 中"
    exit 1
}
$firstTime = -not (Test-Path -LiteralPath (Join-Path $BackendDir ".env"))
if ($firstTime) {
    Write-Warn "未检测到 backend/.env，从 .env.example 自动生成（首次运行）"
    Copy-Item -LiteralPath (Join-Path $BackendDir ".env.example") -Destination (Join-Path $BackendDir ".env")
}
if (-not (Initialize-BackendEnv -FirstTime:$firstTime)) {
    exit 1
}

Write-Title "启动服务"
$backendOk = Start-BackendService
$frontendOk = Start-FrontendService

Write-Title "启动结果"
@(
    [pscustomobject]@{
        服务 = "后端 API（Django）"
        地址 = "http://localhost:$BackendPort/api"
        状态 = $(if ($backendOk) { "运行中" } else { "未启动（见上方提示）" })
        日志 = $(if ($backendOk -and $script:LogTargets["后端 Django"]) { $script:LogTargets["后端 Django"] } else { "-" })
    },
    [pscustomobject]@{
        服务 = "前端页面（Vite）"
        地址 = "http://localhost:$FrontendPort"
        状态 = $(if ($frontendOk) { "运行中" } else { "未启动（见上方提示）" })
        日志 = $(if ($frontendOk -and $script:LogTargets["前端 Vite"]) { $script:LogTargets["前端 Vite"] } else { "-" })
    }
) | Format-Table -AutoSize

if ($backendOk -and $frontendOk) {
    Write-Ok "演示账号：admin / 123456（其余演示账号见 README.md）"
    if ($script:LogTargets["后端 Django"] -like "日志文件*") {
        Write-Info "实时日志：Get-Content $BackendLog -Wait"
    }
    Write-Info "停止服务：.\start.ps1 -Stop（或 stop.bat）"
    if (-not $NoBrowser) {
        Start-Process "http://localhost:$FrontendPort"
    }
    exit 0
}

Write-Err "存在未成功启动的服务，请根据上方提示与日志排查"
exit 1
