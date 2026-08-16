# 一键打包脚本（Windows PowerShell）
# 产出:
#   dist_exe/FundAI/                   绿色版（免安装，整个文件夹拷走即可）
#   dist_exe/FundAI-Setup-0.1.0.exe   安装器（Inno Setup，含开始菜单/桌面快捷方式/卸载）
#
# 用法: powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Backend = Join-Path $Root "backend"
$Tools = Join-Path $Root ".tmp\tools"
New-Item -ItemType Directory -Force -Path $Tools | Out-Null
$env:TMP = Join-Path $Root ".tmp"
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null

Push-Location $Backend
try {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        python -m venv .venv
    }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller

    # 1) 构建前端（若 dist 不存在）
    $FrontendDist = Join-Path $Root "frontend\dist"
    if (-not (Test-Path (Join-Path $FrontendDist "index.html"))) {
        Push-Location (Join-Path $Root "frontend")
        npm install
        npm run build
        Pop-Location
    }

    # 2) PyInstaller 打包（one-folder）
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
    & .\.venv\Scripts\python.exe -m PyInstaller fund_ai.spec --noconfirm --clean

    # 3) 输出到 dist_exe
    $OutDir = Join-Path $Root "dist_exe"
    Remove-Item -Recurse -Force (Join-Path $OutDir "FundAI") -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    Copy-Item -Recurse -Force "dist\FundAI" (Join-Path $OutDir "FundAI")
    Write-Host "绿色版已生成: dist_exe\FundAI\FundAI.exe"

    # 4) Inno Setup 安装器
    $iscc = Join-Path $Tools "inno\ISCC.exe"
    if (-not (Test-Path $iscc)) {
        Write-Host "下载 Inno Setup 编译器…"
        $installer = Join-Path $Tools "is.exe"
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe" -OutFile $installer
        Start-Process -FilePath $installer -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$($Tools)\inno" -Wait
        # 静默安装只带默认语言，补下载中文语言包
        $langDir = Join-Path $Tools "inno\Languages"
        New-Item -ItemType Directory -Force -Path $langDir | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/ChineseSimplified.isl" -OutFile (Join-Path $langDir "ChineseSimplified.isl")
    }
    & $iscc (Join-Path $Root "installer\fund_ai.iss")
    Write-Host "安装器已生成: dist_exe\FundAI-Setup-0.1.0.exe"
}
finally {
    Pop-Location
}
