# 一键安装(Windows): 缺的先自己装, 再建虚拟环境、拉插件、注册进 dsh。
# 可选迁入既有部署: .\install.ps1 -Src C:\path\to\gsuid_core\data
# 只准备环境(插件首次启动时自己调用): .\install.ps1 -EnvOnly
[CmdletBinding()]
param(
    [switch]$EnvOnly,
    [string]$Src = "",
    [string]$Profile = $env:DSH_PROFILE
)

$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 默认不因外部程序失败而停; 显式查 LASTEXITCODE
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}
# 5.1 读 UTF-8 源会按系统代码页解; 本文件存 UTF-16 LE, 输出跟控制台代码页对齐
if ($PSVersionTable.PSVersion.Major -lt 6) {
    try {
        $OutputEncoding = [Console]::OutputEncoding
    } catch {}
}
if (-not $Profile) { $Profile = "web" }

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Service = Join-Path $Root "service"
$Py = Join-Path $Service ".venv\Scripts\python.exe"
# 计算内核按 CPython 版本分发, 仅这些版本有对应包
$Supported = @("3.13", "3.12", "3.11", "3.10")
$PythonVersion = if ($env:PYTHON_VERSION) { $env:PYTHON_VERSION } else { "3.13" }

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host $msg -ForegroundColor Red; exit 1 }
function Has($name) { $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }
function Check($msg) {
    if ($LASTEXITCODE -ne 0) { Fail $msg }
}
function Refresh-EnvPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = @(
        $machine, $user,
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin"),
        (Join-Path $env:LOCALAPPDATA "Programs\Git\cmd"),
        "C:\Program Files\Git\cmd"
    ) -join ";"
}

if ($Supported -notcontains $PythonVersion) {
    Fail "Python $PythonVersion 不受支持, 可选: $($Supported -join ' ')"
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {}

Refresh-EnvPath

if (-not (Has "uv")) {
    Step "安装 uv"
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Write-Host "uv 官方安装失败, 尝试 pip" -ForegroundColor Yellow
    }
    Refresh-EnvPath
    if (-not (Has "uv")) {
        $pyCmd = $null
        $pyArgs = @("-m", "pip", "install", "--user", "-q", "uv")
        if (Has "py") {
            $pyCmd = "py"
            $pyArgs = @("-3") + $pyArgs
        } elseif (Has "python") {
            $pyCmd = "python"
        }
        if ($pyCmd) {
            & $pyCmd @pyArgs 2>$null
            Refresh-EnvPath
        }
    }
}
if (-not (Has "uv")) { Fail "缺少 uv 且自动安装失败, 请手工装: irm https://astral.sh/uv/install.ps1 | iex" }

if (-not (Has "git")) {
    Step "安装 git"
    if (Has "winget") {
        winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity
    }
    Refresh-EnvPath
    if (-not (Has "git") -and (Has "choco")) {
        choco install git -y
        Refresh-EnvPath
    }
    if (-not (Has "git") -and (Has "scoop")) {
        scoop install git
        Refresh-EnvPath
    }
}
if (-not (Has "git")) { Fail "缺少 git 且自动安装失败, 请: winget install Git.Git" }

if (-not $EnvOnly -and -not (Has "dsh")) {
    if (Has "npm") {
        Step "安装 dsh (npm -g @deepseek-ai/dsh)"
        npm install -g @deepseek-ai/dsh
        Refresh-EnvPath
    }
    if (-not (Has "dsh")) { Fail "缺少 dsh, 请先安装 DeepSeek Harness: npm i -g @deepseek-ai/dsh" }
}

Step "准备 Python $PythonVersion"
# 系统没有对应版本时, uv 直接拉官方构建, 不必先装 python.org
uv python install $PythonVersion
if ($LASTEXITCODE -ne 0) {
    Write-Host "uv python install 未成功, 将尝试用已有解释器建 venv" -ForegroundColor Yellow
}

Step "创建虚拟环境 (Python $PythonVersion)"
Push-Location $Service
try {
    if (-not (Test-Path $Py)) {
        uv venv --python $PythonVersion .venv
        Check "创建虚拟环境失败 (uv python install 后仍无法取得 Python $PythonVersion)"
    }
    if (-not (Test-Path $Py)) {
        Fail "未找到 $Py; 删掉 service\.venv 重跑"
    }
    $actual = & $Py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    Check "无法启动虚拟环境解释器"
    if ($Supported -notcontains $actual) {
        Fail "虚拟环境是 Python $actual, 不在支持范围; 删掉 service\.venv 重跑"
    }

    Step "安装依赖"
    uv pip install --python $Py -q -r pyproject.toml
    Check "安装依赖失败"
    & $Py -c @"
import importlib.util as u, sys
need = ('cv2', 'cryptography', 'fastapi', 'sqlmodel', 'PIL', 'jinja2', 'lxml', 'msgspec')
missing = [n for n in need if u.find_spec(n) is None]
sys.exit('依赖缺失: ' + ', '.join(missing)) if missing else print('依赖自检通过')
"@
    Check "依赖自检未通过"

    Step "拉取插件"
    & $Py tools\update_plugins.py
    Check "拉取上游插件失败"

    Step "初始化数据目录"
    if ($Src) {
        & $Py tools\migrate.py --src $Src
    } else {
        & $Py tools\migrate.py
    }
    Check "初始化数据目录失败"
} finally {
    Pop-Location
}

if ($EnvOnly) {
    Write-Host "`n环境就绪。"
    exit 0
}

Step "注册进 dsh profile: $Profile"
dsh plugin --profile $Profile add "file:$Root"
Check "dsh plugin add 失败"
# 加载器按自身位置解析裸包名, 这里补一条目录联接
# Junction 不需要管理员/开发者模式; 失败不致命
$dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$profilePkg = Join-Path $dshHome "profiles\$Profile\node_modules\dsh-plugin-waves"
$dshCmd = $null
$dshInfo = Get-Command dsh -ErrorAction SilentlyContinue
if ($dshInfo) { $dshCmd = $dshInfo.Source }
if ($dshCmd -and (Test-Path $profilePkg)) {
    $dshNm = Join-Path (Split-Path -Parent $dshCmd) "node_modules"
    if (Test-Path $dshNm) {
        $link = Join-Path $dshNm "dsh-plugin-waves"
        if (-not (Test-Path $link)) {
            try {
                New-Item -ItemType Junction -Path $link -Target $profilePkg -ErrorAction Stop | Out-Null
            } catch {}
        }
    }
}
if (Has "node") {
    $nodeVer = & node -v 2>$null
    if ($nodeVer -match '^v(\d+)' -and [int]$Matches[1] -lt 22) {
        Write-Host "`n注意: 当前 node 为 $nodeVer, dsh 需要 22+, 启动前请切换" -ForegroundColor Yellow
    }
}

Write-Host @"

安装完成。

启动:   dsh web
自检:   cd $Service ; .venv\Scripts\python.exe tools\regression.py

首次使用先在对话里绑定账号:
  ww登录            取得并保存登录态
  ww绑定<特征码>     只查询公开数据时用这个

伤害计算与排行需要 WavesToken, 填在
  $Service\data\XutheringWavesUID\config.json
申请方式见 README。
"@
