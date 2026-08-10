# 运行后端测试（Django 标准测试入口）
# 在 backend 目录下执行：powershell -File scripts/test.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

python manage.py test build_protection_service -v 2
