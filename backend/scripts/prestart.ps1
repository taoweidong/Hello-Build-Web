# 迁移数据库并创建超级用户
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
python manage.py makemigrations build_protection_service
python manage.py migrate
python manage.py seed