# 开发辅助脚本（Windows PowerShell）
# 一键启动前端 dev server（/api 自动代理到 localhost:8000）

Set-Location (Join-Path $PSScriptRoot "..\frontend")
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run dev
