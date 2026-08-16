# 开发辅助脚本（Windows PowerShell）
# 运行后端测试

Set-Location (Join-Path $PSScriptRoot "..\backend")
$env:TMP = Join-Path (Get-Location) "..\.tmp"
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
$env:TEMP = $env:TMP
& .\.venv\Scripts\python.exe -m pytest tests -v
