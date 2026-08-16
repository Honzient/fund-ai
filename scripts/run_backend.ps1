# 开发辅助脚本（Windows PowerShell）
# 一键启动后端（先 cd 到 backend 目录，虚拟环境名为 .venv）

param(
    [int]$Port = 8000
)

$env:TMP = Join-Path (Get-Location) "..\.tmp"
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
$env:TEMP = $env:TMP

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}
if (-not (Test-Path ".env")) {
    Copy-Item "..\.env.example" ".env"
    Write-Host "已从 .env.example 创建 backend/.env，请按需填写 DEEPSEEK_API_KEY"
}
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port $Port --reload
