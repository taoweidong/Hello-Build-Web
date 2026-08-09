# 启动前置流程（对齐模板 scripts/prestart.sh 的 Windows 版本）
# 在 backend 目录下执行：powershell -File scripts/prestart.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 等待数据库就绪
python -m app.backend_pre_start

# 执行数据库迁移
alembic upgrade head

# 写入初始数据
python -m app.initial_data
