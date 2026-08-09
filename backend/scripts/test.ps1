# 运行后端测试（对齐模板 scripts/test.sh 的 Windows 版本）
# 在 backend 目录下执行：powershell -File scripts/test.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

pytest
