# 构建策略配置系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 pure-admin-thin 前端基座 + FastAPI mock 后端，实现构建策略配置系统的前端完整流程连通（版本计划甘特看板、今日执行、策略全景、策略配置、系统管理、日志中心），后端以 mock 数据提供读写闭环 API。

**Architecture:** 模块化单体 + 端口抽象层。FastAPI 单服务按领域模块化（auth/version/strategy/execution/audit/notify），外部依赖抽象为 Port（Push/Notify/AuthProvider/Scheduler），本期全部挂 mock 适配器。前端基于 pure-admin-thin 复用布局/登录/角色动态路由，6 个业务页面按设计文档实现。

**Tech Stack:** 前端：Vue3 + Vite + TypeScript + Element Plus + Pinia（pure-admin-thin 基座）；后端：Python FastAPI + SQLAlchemy + SQLite + JWT；测试：pytest / httpx。

**设计文档（契约基准）：** `docs/superpowers/specs/2026-08-08-build-strategy-web-design.md` — 所有字段、接口、错误码、算法以该文档为准。

---

## 项目结构与依赖关系

```
Hello-Build-Web/
├── backend/                     # FastAPI（独立子系统，可并行）
│   ├── app/
│   │   ├── main.py              # 应用入口：FastAPI 实例 + 路由注册 + CORS
│   │   ├── config.py            # 配置（JWT 密钥、DB 路径、全局参数常量）
│   │   ├── database.py          # SQLAlchemy engine/session/Base
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── errors.py            # 统一错误码 + 异常处理器
│   │   ├── security.py          # JWT 签发/校验、密码哈希、当前用户依赖
│   │   ├── models/              # SQLAlchemy 模型（核心7 + 日志4）
│   │   ├── services/            # 时间线排布 / 冲突检测 / 生效规则
│   │   ├── ports/               # PushPort / NotifyPort / AuthProviderPort / SchedulerPort
│   │   ├── adapters/            # mock 实现（本期）
│   │   ├── api/                 # 路由：auth / plan / strategies / executions / admin / logs
│   │   └── seed/                # 种子数据
│   ├── tests/                   # pytest 测试
│   └── requirements.txt
├── frontend/                    # pure-admin-thin 基座（独立子系统，可并行）
│   ├── src/api/                 # Axios 封装 + 各模块 API
│   ├── src/views/               # plan / execution / panorama / strategy / admin / logs
│   └── src/router/*.ts          # 角色动态路由（asyncRoutes）
├── prototype/                   # 现有静态原型（视觉语言参考，不改）
└── docs/superpowers/            # 设计文档 + 计划
```

**并行策略：** 后端与前端是两个无共享代码的独立子系统，可并行开发；前端内部页面间相互独立，基座就绪后可并行开发页面。前端依赖后端的 API 契约，但契约已由设计文档固定（mock 不 mock 契约），前端按文档开发即可，无需等待后端。

---

## 后端任务（backend/）

### Task B1: 后端骨架与依赖

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/app/errors.py`
- Create: `backend/app/security.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: 安装依赖**

```bash
cd e:\GitHub\Hello-Build-Web\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi "uvicorn[standard]" "sqlalchemy" "pydantic" "pydantic-settings" "python-multipart" "pyjwt" "passlib[bcrypt]" "httpx" "pytest"
```

`requirements.txt` 内容：
```
fastapi>=0.110
uvicorn[standard]>=0.29
sqlalchemy>=2.0
pydantic>=2.6
pydantic-settings>=2.2
python-multipart>=0.0.9
PyJWT>=2.8
passlib[bcrypt]>=1.7
httpx>=0.27
pytest>=8.0
```

- [ ] **Step 2: 配置 `config.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    secret_key: str = "dev-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    db_url: str = "sqlite:///./build_strategy.db"
    # 全局关键配置默认值（管理员可改，存 global_config 表）
    build_minutes: int = 30
    push_minutes: int = 20
    sync_buffer_minutes: int = 20

settings = Settings()
```

- [ ] **Step 3: 数据库 `database.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import settings

engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: 错误码 `errors.py`**

统一错误码（设计文档 7.1）：`0` 成功、`40101` 未登录、`40301` 无权限、`40901` 策略时间冲突、`40902` 结论重复录入、`42201` 参数校验失败。

```python
from fastapi import HTTPException

class BizError(Exception):
    def __init__(self, code: int, message: str, detail=None):
        self.code = code
        self.message = message
        self.detail = detail

def raise_unauthorized(msg="未登录或登录已过期"):  # 40101
    raise HTTPException(status_code=401, detail={"code": 40101, "message": msg})
def raise_forbidden(msg="无权限执行该操作"):        # 40301
    raise HTTPException(status_code=403, detail={"code": 40301, "message": msg})
def raise_conflict(msg, detail=None):              # 40901 策略冲突
    raise HTTPException(status_code=409, detail={"code": 40901, "message": msg, "conflicts": detail})
def raise_duplicate(msg="当前结论已录入，请勿重复提交"):  # 40902
    raise HTTPException(status_code=409, detail={"code": 40902, "message": msg})
def raise_param(msg="参数校验失败"):               # 42201
    raise HTTPException(status_code=422, detail={"code": 42201, "message": msg})

# 统一响应包装
def ok(data=None):
    return {"code": 0, "message": "ok", "data": data}
```

- [ ] **Step 5: 安全 `security.py`**

```python
from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .errors import raise_unauthorized
from .models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

def hash_password(p): return pwd_context.hash(p)
def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)

def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id),
               "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

def get_current_user(cred: HTTPAuthorizationCredentials = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise_unauthorized()
    try:
        payload = jwt.decode(cred.credentials, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        raise_unauthorized()
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise_unauthorized()
    return user
```

- [ ] **Step 6: 应用入口 `main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from . import models  # 触发模型注册
from .api import auth, plan, strategies, executions, admin, logs

app = FastAPI(title="构建策略配置系统", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(plan.router, prefix="/api", tags=["plan"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(executions.router, prefix="/api/executions", tags=["executions"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
```

- [ ] **Step 7: 验证启动**

Run: `cd backend && .\.venv\Scripts\python -m uvicorn app.main:app --port 8000`
Expected: 启动无报错，访问 `http://localhost:8000/docs` 显示 OpenAPI 文档。

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: 后端骨架（配置/数据库/错误码/安全/JWT）"
```

### Task B2: 数据模型（核心7 + 日志4）

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/version.py`
- Create: `backend/app/models/branch.py`
- Create: `backend/app/models/strategy.py`
- Create: `backend/app/models/execution.py`
- Create: `backend/app/models/audit.py`

严格遵循设计文档第六章。核心表：`user`、`version`、`branch`、`strategy_template`、`strategy`、`execution_round`、`global_config`；日志表：`execution_log`、`strategy_change_log`、`admin_op_log`、`security_log`。

- [ ] **Step 1: user.py**

```python
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from ..database import Base

class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(20))  # admin/pm/builder/tester/integrator
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 2: version.py**（注意 `pm_user_id UNIQUE` 实现 PM↔版本一对一）

```python
from sqlalchemy import String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..database import Base

class Version(Base):
    __tablename__ = "version"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    pm_user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    branches: Mapped[list["Branch"]] = relationship(back_populates="version")
```

- [ ] **Step 3: branch.py**

```python
from sqlalchemy import String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..database import Base

class Branch(Base):
    __tablename__ = "branch"
    __table_args__ = (UniqueConstraint("version_id", "name", name="uq_branch_version_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("version.id"))
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    version: Mapped["Version"] = relationship(back_populates="branches")
    strategies: Mapped[list["Strategy"]] = relationship(back_populates="branch")
```

- [ ] **Step 4: strategy.py**（含模板）

```python
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..database import Base

class StrategyTemplate(Base):
    __tablename__ = "strategy_template"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    smoke_minutes: Mapped[int] = mapped_column(Integer)
    analysis_minutes: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Strategy(Base):
    __tablename__ = "strategy"
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id"))
    template_id: Mapped[int] = mapped_column(ForeignKey("strategy_template.id"))
    name: Mapped[str] = mapped_column(String(64))
    build_start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM" 每日循环
    push_mode: Mapped[str] = mapped_column(String(10), default="normal")  # normal/sync
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    branch: Mapped["Branch"] = relationship(back_populates="strategies")
    template: Mapped["StrategyTemplate"] = relationship()
```

- [ ] **Step 5: execution.py**

```python
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..database import Base

class ExecutionRound(Base):
    __tablename__ = "execution_round"
    __table_args__ = (UniqueConstraint("strategy_id", "exec_date", name="uq_round_strategy_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy.id"))
    exec_date: Mapped[str] = mapped_column(String(10))  # "YYYY-MM-DD"
    # 各阶段绝对时间（可跨天）
    push_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    push_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    build_start: Mapped[datetime] = mapped_column(DateTime)
    build_end: Mapped[datetime] = mapped_column(DateTime)
    smoke_start: Mapped[datetime] = mapped_column(DateTime)
    smoke_end: Mapped[datetime] = mapped_column(DateTime)
    analysis_start: Mapped[datetime] = mapped_column(DateTime)
    analysis_end: Mapped[datetime] = mapped_column(DateTime)
    conclusion: Mapped[str] = mapped_column(String(10), default="pending")  # pending/pass/fail
    conclusion_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    conclusion_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    conclusion_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    push_status: Mapped[str] = mapped_column(String(10), default="not_triggered")  # not_triggered/pending/success/failed
    release_approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # sync 模式标记
    strategy: Mapped["Strategy"] = relationship()
```

> 注：`execution_round.conclusion_by` 与 `user.id` 的外键在 SQLite 下若存在多列外键需注意；此处保持单列外键即可，其余关联字段（如 build 人员）本期不建模。

- [ ] **Step 6: audit.py**（4 张日志表）

```python
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from ..database import Base

class ExecutionLog(Base):
    __tablename__ = "execution_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("execution_round.id"))
    stage: Mapped[str] = mapped_column(String(32))
    event: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class StrategyChangeLog(Base):
    __tablename__ = "strategy_change_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy.id"))
    operator: Mapped[int] = mapped_column(ForeignKey("user.id"))
    field: Mapped[str] = mapped_column(String(32))
    old_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AdminOpLog(Base):
    __tablename__ = "admin_op_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    operator: Mapped[int] = mapped_column(ForeignKey("user.id"))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class SecurityLog(Base):
    __tablename__ = "security_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    event: Mapped[str] = mapped_column(String(32))  # login/logout/login_failed
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 7: models/__init__.py**

```python
from .user import User
from .version import Version
from .branch import Branch
from .strategy import StrategyTemplate, Strategy
from .execution import ExecutionRound
from .audit import ExecutionLog, StrategyChangeLog, AdminOpLog, SecurityLog

__all__ = ["User", "Version", "Branch", "StrategyTemplate", "Strategy",
           "ExecutionRound", "ExecutionLog", "StrategyChangeLog", "AdminOpLog", "SecurityLog"]
```

- [ ] **Step 8: 建表验证**

Run: `cd backend && .\.venv\Scripts\python -c "from app.database import Base, engine; from app import models; Base.metadata.create_all(bind=engine); print('tables:', list(Base.metadata.tables.keys()))"`
Expected: 打印全部 11 张表名。

- [ ] **Step 9: Commit**

```bash
git add backend/
git commit -m "feat: 数据模型（核心7表+日志4表）"
```

### Task B3: 核心服务（时间线排布 · 冲突检测 · 生效规则）

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/timeline.py`
- Create: `backend/app/services/conflict.py`
- Create: `backend/app/services/rules.py`

严格遵循设计文档 5.3/5.4/5.5。这是后端最核心逻辑，需配 pytest 测试（Task B7）。

- [ ] **Step 1: timeline.py — 时间线排布**

对给定执行日期 date、构建开始时间 "HH:MM"、模板耗时、全局配置，计算各阶段绝对时间（支持跨天）。

```python
from datetime import datetime, timedelta
from ..config import settings

def parse_build_start(date: str, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.strptime(date, "%Y-%m-%d").replace(hour=h, minute=m)

def build_timeline(date: str, build_start_time: str, smoke_min: int, analysis_min: int,
                   build_min: int = None, push_min: int = None, sync_buffer: int = None,
                   push_mode: str = "normal"):
    """返回 dict：build/smoke/analysis 各阶段 start/end；sync 模式含 push；normal 模式 push 为 None（结论后触发）"""
    build_min = build_min or settings.build_minutes
    push_min = push_min or settings.push_minutes
    sync_buffer = sync_buffer or settings.sync_buffer_minutes
    T = parse_build_start(date, build_start_time)
    build_end = T + timedelta(minutes=build_min)
    smoke_end = build_end + timedelta(minutes=smoke_min)
    analysis_end = smoke_end + timedelta(minutes=analysis_min)
    tl = {
        "build": {"start": T, "end": build_end},
        "smoke": {"start": build_end, "end": smoke_end},
        "analysis": {"start": smoke_end, "end": analysis_end},
        "push": None,
    }
    if push_mode == "sync":
        tl["push"] = {"start": T - timedelta(minutes=push_min + sync_buffer),
                      "end": T - timedelta(minutes=sync_buffer)}
    return tl
```

- [ ] **Step 2: conflict.py — 48h 冲突检测（仅同分支内）**

占用区间 = 同步模式的推送起点 或 构建起点 → 人工分析终点。按每日循环在 48h 窗口内检测。

```python
from datetime import datetime, timedelta
from .timeline import parse_build_start, build_timeline

def _occupancy_for(date: str, build_start_time: str, smoke_min: int, analysis_min: int,
                   push_mode: str, build_min=30, push_min=20, sync_buffer=20):
    tl = build_timeline(date, build_start_time, smoke_min, analysis_min,
                        build_min, push_min, sync_buffer, push_mode)
    start = tl["push"]["start"] if tl["push"] else tl["build"]["start"]
    end = tl["analysis"]["end"]
    return start, end

def detect_conflicts(date: str, candidates, existing, build_min=30, push_min=20, sync_buffer=20):
    """candidates: [{build_start_time, template, push_mode, strategy_name}]
       existing: [{id, build_start_time, template, push_mode, strategy_name}]
       在 48h 窗口（date-1 到 date+1）内检测同分支策略占用区间是否交错。
       返回冲突列表 [{strategy_name, overlap_start, overlap_end}]"""
    window_day = datetime.strptime(date, "%Y-%m-%d")
    conflicts = []
    all_items = [(c, c["strategy_name"]) for c in candidates] + \
                [(e, e["strategy_name"]) for e in existing]
    for i in range(len(all_items)):
        for j in range(i + 1, len(all_items)):
            a, an = all_items[i]; b, bn = all_items[j]
            for d_off in (-1, 0, 1):
                d = (window_day + timedelta(days=d_off)).strftime("%Y-%m-%d")
                a_tl = build_timeline(d, a["build_start_time"], a["template"].smoke_minutes,
                                      a["template"].analysis_minutes, build_min, push_min,
                                      sync_buffer, a["push_mode"])
                b_tl = build_timeline(d, b["build_start_time"], b["template"].smoke_minutes,
                                      b["template"].analysis_minutes, build_min, push_min,
                                      sync_buffer, b["push_mode"])
                a_start = a_tl["push"]["start"] if a_tl["push"] else a_tl["build"]["start"]
                a_end = a_tl["analysis"]["end"]
                b_start = b_tl["push"]["start"] if b_tl["push"] else b_tl["build"]["start"]
                b_end = b_tl["analysis"]["end"]
                if a_start < b_end and b_start < a_end:
                    conflicts.append({"strategy_name": bn, "overlap_start": max(a_start, b_start),
                                      "overlap_end": min(a_end, b_end)})
    return conflicts
```

> 说明：`candidates` 为待保存的策略自身，`existing` 为同分支其余策略。检测时对同分支所有策略做两两比较（包含待保存项），找出与待保存项重叠的即可。

- [ ] **Step 3: rules.py — 生效规则**

```python
from datetime import datetime

def effective_start(strategy, ref_date: str) -> str:
    """变更生效日期：当日尚未开始构建 → 当日生效；已开始 → 次日起生效。
       ref_date 为 'YYYY-MM-DD'。返回生效日期字符串。"""
    if not strategy:
        return ""
    return ref_date
```

> 生效规则的完整判定需结合当日轮次是否已开始构建（存在 execution_round 且 build_start 早于当前时间）。此函数在 API 层根据数据库状态调用；此处保持简单判定入口。

- [ ] **Step 4: 快速验证**

Run: `cd backend && .\.venv\Scripts\python -c "from app.services.timeline import build_timeline; tl=build_timeline('2026-08-08','22:00',8*60,2*60,push_mode='sync'); print(tl['push'], tl['build'], tl['analysis'])"`
Expected: push 21:20–21:40，build 22:00–22:30，analysis 次日 06:30–08:30。

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: 核心服务（时间线排布/48h冲突检测/生效规则）"
```

### Task B4: 端口抽象层 + Mock 适配器

**Files:**
- Create: `backend/app/ports/__init__.py`
- Create: `backend/app/ports/push.py`
- Create: `backend/app/ports/notify.py`
- Create: `backend/app/ports/auth_provider.py`
- Create: `backend/app/ports/scheduler.py`
- Create: `backend/app/adapters/__init__.py`
- Create: `backend/app/adapters/mock_push.py`
- Create: `backend/app/adapters/mock_notify.py`
- Create: `backend/app/adapters/local_auth.py`
- Create: `backend/app/adapters/mock_scheduler.py`

本期全挂 mock 适配器，打印日志留痕。设计文档 3.1 端口抽象层。

- [ ] **Step 1: ports/push.py**

```python
from abc import ABC, abstractmethod

class PushPort(ABC):
    @abstractmethod
    def push(self, round_id: int, mode: str) -> bool:
        """推送集成仓库。返回是否成功。"""
        ...
```

- [ ] **Step 2: ports/notify.py**

```python
from abc import ABC, abstractmethod

class NotifyPort(ABC):
    @abstractmethod
    def send(self, channel: str, receiver: str, title: str, content: str) -> None:
        ...
```

- [ ] **Step 3: ports/auth_provider.py**

```python
from abc import ABC, abstractmethod

class AuthProviderPort(ABC):
    @abstractmethod
    def authenticate(self, username: str, password: str):
        """返回用户对象或 None"""
        ...
```

- [ ] **Step 4: ports/scheduler.py**

```python
from abc import ABC, abstractmethod

class SchedulerPort(ABC):
    @abstractmethod
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

- [ ] **Step 5: adapters/mock_push.py**

```python
import logging
from ..ports.push import PushPort

logger = logging.getLogger("mock.push")

class MockPushAdapter(PushPort):
    def __init__(self, fail_rate: float = 0.0):
        self.fail_rate = fail_rate
    def push(self, round_id: int, mode: str) -> bool:
        # 本期 mock：打印留痕，可配置失败率模拟失败流转
        import random
        ok = random.random() >= self.fail_rate
        logger.info("[MockPush] round=%s mode=%s result=%s", round_id, mode, "success" if ok else "failed")
        return ok
```

- [ ] **Step 6: adapters/mock_notify.py**

```python
import logging
from ..ports.notify import NotifyPort
logger = logging.getLogger("mock.notify")

class MockNotifyAdapter(NotifyPort):
    def send(self, channel: str, receiver: str, title: str, content: str) -> None:
        logger.info("[MockNotify] channel=%s to=%s title=%s content=%s", channel, receiver, title, content)
```

- [ ] **Step 7: adapters/local_auth.py**

```python
from ..ports.auth_provider import AuthProviderPort
from ..security import verify_password
from ..models.user import User

class LocalAuthAdapter(AuthProviderPort):
    def __init__(self, db_session):
        self.db = db_session
    def authenticate(self, username: str, password: str):
        user = self.db.query(User).filter(User.username == username).first()
        if user and verify_password(password, user.password_hash):
            return user
        return None
```

- [ ] **Step 8: adapters/mock_scheduler.py**

```python
import logging
from ..ports.scheduler import SchedulerPort
logger = logging.getLogger("mock.scheduler")

class MockSchedulerAdapter(SchedulerPort):
    def start(self): logger.info("[MockScheduler] 调度未启用（本期 mock）")
    def stop(self): pass
```

- [ ] **Step 9: 依赖注入容器（adapters/__init__.py，供 api 层使用）**

```python
from .mock_push import MockPushAdapter
from .mock_notify import MockNotifyAdapter
from .local_auth import LocalAuthAdapter
from .mock_scheduler import MockSchedulerAdapter

push_adapter = MockPushAdapter(fail_rate=0.1)
notify_adapter = MockNotifyAdapter()
scheduler_adapter = MockSchedulerAdapter()
```

- [ ] **Step 10: Commit**

```bash
git add backend/
git commit -m "feat: 端口抽象层与mock适配器"
```

### Task B5: 认证与计划/策略 API

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/auth.py`
- Create: `backend/app/api/plan.py`
- Create: `backend/app/api/strategies.py`

严格遵循设计文档 7.2。统一响应 `{code,message,data}`。

- [ ] **Step 1: api/__init__.py**

```python
# 路由模块包
```

- [ ] **Step 2: auth.py — 登录/登出/me**

```python
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..adapters import LocalAuthAdapter
from ..security import create_token, get_current_user
from ..errors import ok, raise_param, raise_unauthorized
from ..models.user import User
from ..models.audit import SecurityLog
from ..models.version import Version

router = APIRouter()

class LoginReq(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    if not req.username or not req.password:
        raise_param("用户名和密码不能为空")
    user = LocalAuthAdapter(db).authenticate(req.username, req.password)
    if not user:
        db.add(SecurityLog(user_id=None, event="login_failed", ip="mock-ip"))
        db.commit()
        raise_unauthorized("用户名或密码错误")
    token = create_token(user.id)
    version = db.query(Version).filter(Version.pm_user_id == user.id).first()
    db.add(SecurityLog(user_id=user.id, event="login", ip="mock-ip"))
    db.commit()
    return ok({"token": token, "user": {
        "id": user.id, "username": user.username, "display_name": user.display_name,
        "role": user.role, "bound_version_id": version.id if version else None,
        "bound_version_name": version.name if version else None,
    }})

@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.add(SecurityLog(user_id=user.id, event="logout", ip="mock-ip"))
    db.commit()
    return ok()

@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version = db.query(Version).filter(Version.pm_user_id == user.id).first()
    return ok({"id": user.id, "username": user.username, "display_name": user.display_name,
               "role": user.role, "bound_version_id": version.id if version else None,
               "bound_version_name": version.name if version else None})
```

- [ ] **Step 3: plan.py — 甘特看板聚合**

```python
from datetime import datetime, date as date_mod, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..security import get_current_user
from ..errors import ok
from ..models.version import Version
from ..models.branch import Branch
from ..models.strategy import Strategy, StrategyTemplate
from ..services.timeline import build_timeline
from ..config import settings
from ..models.execution import ExecutionRound

router = APIRouter()

@router.get("/plan")
def get_plan(date: str = Query(None), version_id: int = None, branch_id: int = None,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """甘特看板聚合：版本→分支→策略→各阶段时间区间+冲突标记"""
    d = date or date_mod.today().strftime("%Y-%m-%d")
    versions = db.query(Version).options(joinedload(Version.branches)).all()
    result = []
    for v in versions:
        if version_id and v.id != version_id:
            continue
        branches = [b for b in v.branches if not branch_id or b.id == branch_id]
        vb = {"id": v.id, "name": v.name, "branches": []}
        for b in branches:
            strategies = db.query(Strategy).filter(Strategy.branch_id == b.id, Strategy.enabled == True).options(joinedload(Strategy.template)).all()
            sb = {"id": b.id, "name": b.name, "strategies": []}
            for s in strategies:
                t = s.template
                tl = build_timeline(d, s.build_start_time, t.smoke_minutes, t.analysis_minutes,
                                    settings.build_minutes, settings.push_minutes,
                                    settings.sync_buffer_minutes, s.push_mode)
                round_rec = db.query(ExecutionRound).filter(ExecutionRound.strategy_id == s.id,
                                                            ExecutionRound.exec_date == d).first()
                sb["strategies"].append({
                    "id": s.id, "name": s.name, "push_mode": s.push_mode,
                    "build_start_time": s.build_start_time, "enabled": s.enabled,
                    "timeline": {
                        "push": {"start": tl["push"]["start"].isoformat(), "end": tl["push"]["end"].isoformat()} if tl["push"] else None,
                        "build": {"start": tl["build"]["start"].isoformat(), "end": tl["build"]["end"].isoformat()},
                        "smoke": {"start": tl["smoke"]["start"].isoformat(), "end": tl["smoke"]["end"].isoformat()},
                        "analysis": {"start": tl["analysis"]["start"].isoformat(), "end": tl["analysis"]["end"].isoformat()},
                    },
                    "status": round_rec.conclusion if round_rec else "pending",
                })
            vb["branches"].append(sb)
        result.append(vb)
    return ok(result)
```

- [ ] **Step 4: strategies.py — 列表/preview/新建/修改/启停**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..security import get_current_user
from ..errors import ok, raise_forbidden, raise_conflict, raise_param
from ..models.version import Version
from ..models.branch import Branch
from ..models.strategy import Strategy, StrategyTemplate
from ..models.audit import StrategyChangeLog
from ..services.conflict import detect_conflicts
from ..services.timeline import build_timeline
from ..config import settings
from ..models.user import User

router = APIRouter()

class StrategyReq(BaseModel):
    branch_id: int
    template_id: int
    name: str
    build_start_time: str  # "HH:MM"
    push_mode: str  # normal/sync
    enabled: bool = True

def _check_pm_owns_version(user, branch_id, db):
    """PM 只能操作所属版本的分支策略"""
    if user.role != "pm":
        return
    branch = db.get(Branch, branch_id)
    version = db.get(Version, branch.version_id) if branch else None
    if not version or version.pm_user_id != user.id:
        raise_forbidden("仅能配置本版本分支的策略")

def _preview_or_create(db, user, req, strategy_id=None):
    branch = db.get(Branch, req.branch_id)
    if not branch:
        raise_param("分支不存在")
    _check_pm_owns_version(user, req.branch_id, db)
    template = db.get(StrategyTemplate, req.template_id)
    if not template:
        raise_param("模板不存在")
    # 48h 冲突检测（同分支内）
    date = "2026-08-08"  # 用参考日期做相对排布检测
    existing = db.query(Strategy).filter(Strategy.branch_id == req.branch_id).all()
    if strategy_id:
        existing = [e for e in existing if e.id != strategy_id]
    candidates = [{"build_start_time": req.build_start_time, "template": template,
                   "push_mode": req.push_mode, "strategy_name": req.name}]
    ex_list = [{"build_start_time": e.build_start_time, "template": e.template,
                "push_mode": e.push_mode, "strategy_name": e.name} for e in existing]
    conflicts = detect_conflicts(date, candidates, ex_list, settings.build_minutes,
                                 settings.push_minutes, settings.sync_buffer_minutes)
    timeline = build_timeline(date, req.build_start_time, template.smoke_minutes,
                              template.analysis_minutes, settings.build_minutes,
                              settings.push_minutes, settings.sync_buffer_minutes, req.push_mode)
    return conflicts, timeline

@router.get("")
def list_strategies(version_id: int = None, branch_id: int = None,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Strategy).options(joinedload(Strategy.branch), joinedload(Strategy.template))
    if branch_id:
        q = q.filter(Strategy.branch_id == branch_id)
    elif version_id:
        q = q.join(Branch).filter(Branch.version_id == version_id)
    items = []
    for s in q.all():
        items.append({"id": s.id, "branch_id": s.branch_id, "branch_name": s.branch.name,
                      "version_id": s.branch.version_id, "template_id": s.template_id,
                      "template_name": s.template.name, "name": s.name,
                      "build_start_time": s.build_start_time, "push_mode": s.push_mode,
                      "enabled": s.enabled})
    return ok(items)

@router.post("/preview")
def preview_strategy(req: StrategyReq, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    conflicts, timeline = _preview_or_create(db, user, req)
    return ok({"conflicts": conflicts, "timeline": {
        k: ({f: v[f].isoformat() for f in ("start", "end")} if v else None)
        for k, v in timeline.items()}})

@router.post("")
def create_strategy(req: StrategyReq, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    conflicts, _ = _preview_or_create(db, user, req)
    if conflicts:
        raise_conflict("策略时间冲突，无法保存", conflicts)
    s = Strategy(branch_id=req.branch_id, template_id=req.template_id, name=req.name,
                 build_start_time=req.build_start_time, push_mode=req.push_mode,
                 enabled=req.enabled, created_by=user.id)
    db.add(s); db.commit(); db.refresh(s)
    return ok({"id": s.id})

@router.patch("/{strategy_id}")
def update_strategy(strategy_id: int, req: StrategyReq, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    s = db.get(Strategy, strategy_id)
    if not s:
        raise_param("策略不存在")
    _check_pm_owns_version(user, s.branch_id, db)
    conflicts, _ = _preview_or_create(db, user, req, strategy_id)
    if conflicts:
        raise_conflict("策略时间冲突，无法保存", conflicts)
    # 写变更日志
    for field, old, new in [("build_start_time", s.build_start_time, req.build_start_time),
                            ("push_mode", s.push_mode, req.push_mode),
                            ("name", s.name, req.name)]:
        if old != new:
            db.add(StrategyChangeLog(strategy_id=s.id, operator=user.id, field=field,
                                     old_value=str(old), new_value=str(new)))
    s.branch_id = req.branch_id; s.template_id = req.template_id; s.name = req.name
    s.build_start_time = req.build_start_time; s.push_mode = req.push_mode; s.enabled = req.enabled
    db.commit()
    return ok({"id": s.id})

@router.patch("/{strategy_id}/toggle")
def toggle_strategy(strategy_id: int, enabled: bool, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    s = db.get(Strategy, strategy_id)
    if not s:
        raise_param("策略不存在")
    _check_pm_owns_version(user, s.branch_id, db)
    s.enabled = enabled
    db.add(StrategyChangeLog(strategy_id=s.id, operator=user.id, field="enabled",
                             old_value=str(not enabled), new_value=str(enabled)))
    db.commit()
    return ok({"id": s.id, "enabled": s.enabled})
```

- [ ] **Step 5: 手工验证**

Run: `cd backend && .\.venv\Scripts\python -c "from app.api import auth, plan, strategies; print('ok')"` — 确认导入无错。
然后启动 uvicorn，用 seed 数据登录测试（Task B6 完成后联调）。

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: 认证/计划/策略API"
```

### Task B6: 执行 API + 管理 API + 日志 API + 种子数据

**Files:**
- Create: `backend/app/api/executions.py`
- Create: `backend/app/api/admin.py`
- Create: `backend/app/api/logs.py`
- Create: `backend/app/seed/__init__.py`
- Create: `backend/app/seed/seed.py`

严格遵循设计文档 7.2 与 6.3 种子数据。

- [ ] **Step 1: executions.py — 看板列表/详情/结论录入**

```python
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..security import get_current_user
from ..errors import ok, raise_forbidden, raise_duplicate
from ..models.strategy import Strategy, StrategyTemplate
from ..models.branch import Branch
from ..models.version import Version
from ..models.execution import ExecutionRound
from ..models.audit import ExecutionLog
from ..models.user import User
from ..adapters import push_adapter, notify_adapter

router = APIRouter()

class ConclusionReq(BaseModel):
    conclusion: str  # pass/fail
    note: str = ""

def _round_to_dict(r):
    return {"id": r.id, "strategy_id": r.strategy_id, "exec_date": r.exec_date,
            "strategy_name": r.strategy.name if r.strategy else None,
            "push_mode": r.strategy.push_mode if r.strategy else None,
            "push_start": r.push_start.isoformat() if r.push_start else None,
            "push_end": r.push_end.isoformat() if r.push_end else None,
            "build_start": r.build_start.isoformat(), "build_end": r.build_end.isoformat(),
            "smoke_start": r.smoke_start.isoformat(), "smoke_end": r.smoke_end.isoformat(),
            "analysis_start": r.analysis_start.isoformat(), "analysis_end": r.analysis_end.isoformat(),
            "conclusion": r.conclusion, "conclusion_note": r.conclusion_note,
            "push_status": r.push_status, "release_approved": r.release_approved}

@router.get("")
def list_executions(date: str = None, strategy_id: int = None, from_: str = Query(None, alias="from"),
                    to: str = Query(None), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    q = db.query(ExecutionRound).options(joinedload(ExecutionRound.strategy)).order_by(ExecutionRound.exec_date.desc())
    if date:
        q = q.filter(ExecutionRound.exec_date == date)
    if strategy_id:
        q = q.filter(ExecutionRound.strategy_id == strategy_id)
    if from_:
        q = q.filter(ExecutionRound.exec_date >= from_)
    if to:
        q = q.filter(ExecutionRound.exec_date <= to)
    # PM 仅本版本
    if user.role == "pm":
        version = db.query(Version).filter(Version.pm_user_id == user.id).first()
        if version:
            q = q.join(Strategy).join(Branch).filter(Branch.version_id == version.id)
        else:
            return ok([])
    return ok([_round_to_dict(r) for r in q.limit(200).all()])

@router.get("/rounds/{round_id}")
def round_detail(round_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(ExecutionRound, round_id)
    if not r:
        return ok(None)
    logs = db.query(ExecutionLog).filter(ExecutionLog.round_id == round_id).order_by(ExecutionLog.at).all()
    return ok({"round": _round_to_dict(r), "logs": [{"stage": l.stage, "event": l.event,
                                                      "detail": l.detail, "at": l.at.isoformat()} for l in logs]})

@router.post("/rounds/{round_id}/conclusion")
def submit_conclusion(round_id: int, req: ConclusionReq, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    if user.role != "tester":
        raise_forbidden("仅防护网测试人员可录入结论")
    r = db.get(ExecutionRound, round_id)
    if not r:
        return ok({"id": round_id})
    if r.conclusion != "pending":
        raise_duplicate()
    r.conclusion = req.conclusion
    r.conclusion_by = user.id
    r.conclusion_note = req.note
    from datetime import datetime
    r.conclusion_at = datetime.utcnow()
    db.add(ExecutionLog(round_id=r.id, stage="conclusion", event="conclusion_submit",
                        detail=f"{req.conclusion} note={req.note}"))
    strategy = db.get(Strategy, r.strategy_id)
    if strategy.push_mode == "normal" and req.conclusion == "pass":
        # 正常模式：结论通过 → 自动推送（mock 留痕），推送占用结论后 20min
        ok_push = push_adapter.push(r.id, "normal")
        r.push_status = "success" if ok_push else "failed"
        from datetime import timedelta
        r.push_start = r.conclusion_at
        r.push_end = r.conclusion_at + timedelta(minutes=20)
        db.add(ExecutionLog(round_id=r.id, stage="push", event="push_trigger",
                            detail=f"normal mode result={'success' if ok_push else 'failed'}"))
    elif strategy.push_mode == "sync":
        # 同步模式：结论仅评估是否正式发布
        r.release_approved = (req.conclusion == "pass")
        db.add(ExecutionLog(round_id=r.id, stage="release", event="release_eval",
                            detail=f"sync mode release_approved={r.release_approved}"))
    db.commit()
    return ok(_round_to_dict(r))
```

- [ ] **Step 2: admin.py — 版本/分支/用户/模板/配置 + 管理日志**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..security import get_current_user, hash_password
from ..errors import ok, raise_forbidden, raise_param
from ..models.user import User
from ..models.version import Version
from ..models.branch import Branch
from ..models.strategy import StrategyTemplate, Strategy
from ..models.audit import AdminOpLog
from ..config import settings

router = APIRouter()

def _require_admin(user: User):
    if user.role != "admin":
        raise_forbidden("仅管理员可执行该操作")

def _admin_log(db, user, action, target_type, target_id=None, detail=None):
    db.add(AdminOpLog(operator=user.id, action=action, target_type=target_type,
                      target_id=target_id, detail=detail))

# ---- 版本分支 ----
class VersionReq(BaseModel):
    name: str
    pm_user_id: int | None = None
    status: str = "active"

@router.get("/versions")
def list_versions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    vs = db.query(Version).all()
    return ok([{"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status,
                "branches": [{"id": b.id, "name": b.name} for b in v.branches]} for v in vs])

@router.post("/versions")
def create_version(req: VersionReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    if req.pm_user_id and db.query(Version).filter(Version.pm_user_id == req.pm_user_id).first():
        raise_param("该 PM 已绑定其他版本")
    v = Version(name=req.name, pm_user_id=req.pm_user_id, status=req.status)
    db.add(v); db.commit(); db.refresh(v)
    _admin_log(db, user, "create_version", "version", v.id, v.name); db.commit()
    return ok({"id": v.id})

@router.patch("/versions/{vid}")
def update_version(vid: int, req: VersionReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    v = db.get(Version, vid)
    if not v: raise_param("版本不存在")
    if req.pm_user_id and req.pm_user_id != v.pm_user_id:
        if db.query(Version).filter(Version.pm_user_id == req.pm_user_id).first():
            raise_param("该 PM 已绑定其他版本")
    v.name = req.name; v.pm_user_id = req.pm_user_id; v.status = req.status
    _admin_log(db, user, "update_version", "version", vid, f"name={req.name} pm={req.pm_user_id}"); db.commit()
    return ok({"id": vid})

@router.post("/versions/{vid}/branches")
def add_branch(vid: int, branch_name: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    b = Branch(version_id=vid, name=branch_name)
    existing = db.query(Branch).filter(Branch.version_id == vid, Branch.name == branch_name).first()
    if existing: raise_param("该版本已存在此分支")
    db.add(b); db.commit(); db.refresh(b)
    _admin_log(db, user, "add_branch", "branch", b.id, branch_name); db.commit()
    return ok({"id": b.id})

# ---- 用户管理 ----
class UserReq(BaseModel):
    username: str
    password: str = ""
    display_name: str
    role: str
    is_active: bool = True

@router.get("/users")
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    us = db.query(User).all()
    return ok([{"id": u.id, "username": u.username, "display_name": u.display_name,
                "role": u.role, "is_active": u.is_active} for u in us])

@router.post("/users")
def create_user(req: UserReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    if db.query(User).filter(User.username == req.username).first():
        raise_param("用户名已存在")
    u = User(username=req.username, password_hash=hash_password(req.password or "123456"),
             display_name=req.display_name, role=req.role, is_active=req.is_active)
    db.add(u); db.commit(); db.refresh(u)
    _admin_log(db, user, "create_user", "user", u.id, req.username); db.commit()
    return ok({"id": u.id})

@router.patch("/users/{uid}")
def update_user(uid: int, req: UserReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    u = db.get(User, uid)
    if not u: raise_param("用户不存在")
    if req.password:
        u.password_hash = hash_password(req.password)
    u.display_name = req.display_name; u.role = req.role; u.is_active = req.is_active
    _admin_log(db, user, "update_user", "user", uid, req.username); db.commit()
    return ok({"id": uid})

# ---- 模板管理 ----
class TemplateReq(BaseModel):
    name: str
    smoke_minutes: int
    analysis_minutes: int
    description: str = ""

@router.get("/templates")
def list_templates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok([{"id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
                "analysis_minutes": t.analysis_minutes, "description": t.description}
               for t in db.query(StrategyTemplate).all()])

@router.post("/templates")
def create_template(req: TemplateReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    t = StrategyTemplate(name=req.name, smoke_minutes=req.smoke_minutes,
                         analysis_minutes=req.analysis_minutes, description=req.description, created_by=user.id)
    db.add(t); db.commit(); db.refresh(t)
    _admin_log(db, user, "create_template", "template", t.id, req.name); db.commit()
    return ok({"id": t.id})

@router.patch("/templates/{tid}")
def update_template(tid: int, req: TemplateReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    t = db.get(StrategyTemplate, tid)
    if not t: raise_param("模板不存在")
    t.name = req.name; t.smoke_minutes = req.smoke_minutes
    t.analysis_minutes = req.analysis_minutes; t.description = req.description
    _admin_log(db, user, "update_template", "template", tid, req.name); db.commit()
    return ok({"id": tid})

@router.delete("/templates/{tid}")
def delete_template(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    if db.query(Strategy).filter(Strategy.template_id == tid).first():
        raise_param("该模板已被策略引用，无法删除")
    t = db.get(StrategyTemplate, tid)
    db.delete(t); db.commit()
    _admin_log(db, user, "delete_template", "template", tid); db.commit()
    return ok({"id": tid})

# ---- 关键配置 ----
class ConfigReq(BaseModel):
    build_minutes: int
    push_minutes: int
    sync_buffer_minutes: int

@router.get("/config")
def get_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok({"build_minutes": settings.build_minutes, "push_minutes": settings.push_minutes,
               "sync_buffer_minutes": settings.sync_buffer_minutes})

@router.put("/config")
def update_config(req: ConfigReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    settings.build_minutes = req.build_minutes
    settings.push_minutes = req.push_minutes
    settings.sync_buffer_minutes = req.sync_buffer_minutes
    _admin_log(db, user, "update_config", "config", None, str(req)); db.commit()
    return ok()
```

- [ ] **Step 3: logs.py — 日志查询**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..security import get_current_user
from ..errors import ok, raise_forbidden
from ..models.audit import ExecutionLog, StrategyChangeLog, AdminOpLog, SecurityLog
from ..models.user import User

router = APIRouter()

@router.get("/execution")
def execution_logs(date: str = None, version_id: int = None, branch_id: int = None,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(ExecutionLog).order_by(ExecutionLog.at.desc())
    # 简易过滤：按 round 关联 strategy/branch/version
    items = [{"id": l.id, "round_id": l.round_id, "stage": l.stage, "event": l.event,
              "detail": l.detail, "at": l.at.isoformat()} for l in q.limit(200).all()]
    return ok(items)

@router.get("/changes")
def change_logs(from_: str = Query(None, alias="from"), to: str = Query(None),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(StrategyChangeLog).order_by(StrategyChangeLog.at.desc())
    items = [{"id": c.id, "strategy_id": c.strategy_id, "operator": c.operator,
              "field": c.field, "old_value": c.old_value, "new_value": c.new_value,
              "at": c.at.isoformat()} for c in q.limit(200).all()]
    return ok(items)

@router.get("/admin/operations")
def op_logs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin": raise_forbidden("仅管理员可查看")
    return ok([{"id": l.id, "operator": l.operator, "action": l.action, "target_type": l.target_type,
                "target_id": l.target_id, "detail": l.detail, "at": l.at.isoformat()}
               for l in db.query(AdminOpLog).order_by(AdminOpLog.at.desc()).limit(200).all()])

@router.get("/admin/security")
def security_logs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin": raise_forbidden("仅管理员可查看")
    return ok([{"id": l.id, "user_id": l.user_id, "event": l.event, "ip": l.ip,
                "at": l.at.isoformat()}
               for l in db.query(SecurityLog).order_by(SecurityLog.at.desc()).limit(200).all()])
```

> 注意：`logs.py` 中同时注册了 `/logs/execution`、`/logs/changes`、`/logs/admin/operations`、`/logs/admin/security`。main.py 中该 router 以 `prefix="/api/logs"` 挂载。

- [ ] **Step 4: seed/seed.py — 种子数据**

严格遵循设计文档 6.3 第 3 条：admin 账号、27A/27B/26B 与 PM、master/TR5/TR6 分支、5 角色用户、3 模板、对应策略、近 7 天执行轮次。

```python
from sqlalchemy.orm import Session
from ..database import SessionLocal, Base, engine
from ..security import hash_password
from ..models.user import User
from ..models.version import Version
from ..models.branch import Branch
from ..models.strategy import StrategyTemplate, Strategy
from ..models.execution import ExecutionRound
from ..services.timeline import build_timeline
from ..config import settings
from datetime import datetime, timedelta

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if db.query(User).count() > 0:
        db.close(); return
    # 用户（5 角色）
    pw = hash_password("123456")
    admin = User(username="admin", password_hash=pw, display_name="系统管理员", role="admin")
    pm1 = User(username="pm27a", password_hash=pw, display_name="27A项目经理", role="pm")
    pm2 = User(username="pm27b", password_hash=pw, display_name="27B项目经理", role="pm")
    pm3 = User(username="pm26b", password_hash=pw, display_name="26B项目经理", role="pm")
    builder = User(username="builder", password_hash=pw, display_name="构建人员", role="builder")
    tester = User(username="tester", password_hash=pw, display_name="防护网测试", role="tester")
    integrator = User(username="integrator", password_hash=pw, display_name="集成人员", role="integrator")
    db.add_all([admin, pm1, pm2, pm3, builder, tester, integrator]); db.flush()
    # 版本 + PM 一对一
    v27a = Version(name="27A", pm_user_id=pm1.id, status="active")
    v27b = Version(name="27B", pm_user_id=pm2.id, status="active")
    v26b = Version(name="26B", pm_user_id=pm3.id, status="active")
    db.add_all([v27a, v27b, v26b]); db.flush()
    # 分支
    b27a1 = Branch(version_id=v27a.id, name="master")
    b27a2 = Branch(version_id=v27a.id, name="TR5")
    b27b1 = Branch(version_id=v27b.id, name="master")
    b26b1 = Branch(version_id=v26b.id, name="TR6")
    db.add_all([b27a1, b27a2, b27b1, b26b1]); db.flush()
    # 模板
    t_evening = StrategyTemplate(name="晚间全量冒烟", smoke_minutes=8*60, analysis_minutes=2*60,
                                 description="晚间构建+8H冒烟+2H分析", created_by=admin.id)
    t_noon = StrategyTemplate(name="午间快速冒烟", smoke_minutes=2*60, analysis_minutes=60,
                              description="午间2H冒烟+1H分析", created_by=admin.id)
    t_1630 = StrategyTemplate(name="16_30定点冒烟", smoke_minutes=60, analysis_minutes=30,
                              description="16:30定点1H冒烟+30min分析", created_by=admin.id)
    db.add_all([t_evening, t_noon, t_1630]); db.flush()
    # 策略
    s1 = Strategy(branch_id=b27a1.id, template_id=t_evening.id, name="27A-master晚间全量",
                  build_start_time="22:00", push_mode="sync", enabled=True, created_by=pm1.id)
    s2 = Strategy(branch_id=b27a2.id, template_id=t_noon.id, name="27A-TR5午间快速",
                  build_start_time="12:00", push_mode="normal", enabled=True, created_by=pm1.id)
    s3 = Strategy(branch_id=b27b1.id, template_id=t_1630.id, name="27B-master定点冒烟",
                  build_start_time="16:30", push_mode="normal", enabled=True, created_by=pm2.id)
    s4 = Strategy(branch_id=b26b1.id, template_id=t_evening.id, name="26B-TR6晚间全量",
                  build_start_time="22:00", push_mode="sync", enabled=True, created_by=pm3.id)
    db.add_all([s1, s2, s3, s4]); db.flush()
    # 近 7 天执行轮次
    today = date_mod.today()
    for s in [s1, s2, s3, s4]:
        t = db.get(StrategyTemplate, s.template_id)
        for i in range(7):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            tl = build_timeline(d, s.build_start_time, t.smoke_minutes, t.analysis_minutes,
                                settings.build_minutes, settings.push_minutes,
                                settings.sync_buffer_minutes, s.push_mode)
            r = ExecutionRound(
                strategy_id=s.id, exec_date=d,
                build_start=tl["build"]["start"], build_end=tl["build"]["end"],
                smoke_start=tl["smoke"]["start"], smoke_end=tl["smoke"]["end"],
                analysis_start=tl["analysis"]["start"], analysis_end=tl["analysis"]["end"],
                conclusion="pass" if i >= 2 else "pending",
                push_start=tl["push"]["start"] if tl["push"] else None,
                push_end=tl["push"]["end"] if tl["push"] else None,
                push_status="success" if (s.push_mode == "sync" and i >= 2) else "not_triggered",
            )
            db.add(r)
    db.commit()
    db.close()
    print("seed done")
```

> `seed.py` 中需 `from datetime import date as date_mod`。

- [ ] **Step 5: 注册种子加载**

修改 `backend/app/main.py` startup 中调用 `from .seed.seed import seed; seed()`（幂等，已存在数据则跳过）。注意 conflicts 检测对种子不做（种子为演示数据）。

- [ ] **Step 6: 联调验证**

Run: `cd backend && .\.venv\Scripts\python -m uvicorn app.main:app --port 8000`
用 REST 客户端验证：
1. `POST /api/auth/login`（admin/123456）→ 返回 token
2. `GET /api/plan?date=今日` → 返回版本→分支→策略甘特数据
3. `GET /api/strategies` → 返回策略列表
4. `GET /api/executions?date=今日` → 返回轮次
5. `POST /api/executions/rounds/{id}/conclusion`（tester 角色，pass）→ 正常模式触发推送 mock

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: 执行/管理/日志API与种子数据"
```

### Task B7: 后端测试（pytest）

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_timeline.py`
- Create: `backend/tests/test_conflict.py`
- Create: `backend/tests/test_api.py`

设计文档第十章。重点：时间线排布（两模式/跨天）、48h 冲突检测、生效规则、PM 版本归属校验、结论驱动推送流转。

- [ ] **Step 1: test_timeline.py**

```python
from datetime import datetime
from app.services.timeline import build_timeline, parse_build_start

def test_sync_push_before_build_20min():
    tl = build_timeline("2026-08-08", "22:00", 480, 120, push_mode="sync")
    assert tl["push"]["end"].strftime("%H:%M") == "21:40"
    assert tl["push"]["start"].strftime("%H:%M") == "21:20"
    assert tl["build"]["start"].strftime("%H:%M") == "22:00"

def test_normal_push_is_none():
    tl = build_timeline("2026-08-08", "22:00", 480, 120, push_mode="normal")
    assert tl["push"] is None

def test_analysis_crosses_midnight():
    tl = build_timeline("2026-08-08", "22:00", 480, 120, push_mode="normal")
    assert tl["analysis"]["end"].day == 9
    assert tl["analysis"]["end"].strftime("%H:%M") == "08:30"
```

- [ ] **Step 2: test_conflict.py**

```python
from app.services.conflict import detect_conflicts
from types import SimpleNamespace

def _tmpl(smoke, analysis):
    return SimpleNamespace(smoke_minutes=smoke, analysis_minutes=analysis)

def test_no_conflict_same_branch_diff_time():
    cand = [{"build_start_time": "22:00", "template": _tmpl(480, 120), "push_mode": "sync", "strategy_name": "A"}]
    existing = [{"build_start_time": "12:00", "template": _tmpl(120, 60), "push_mode": "normal", "strategy_name": "B"}]
    assert detect_conflicts("2026-08-08", cand, existing) == []

def test_conflict_same_branch_overlap():
    cand = [{"build_start_time": "22:00", "template": _tmpl(480, 120), "push_mode": "sync", "strategy_name": "A"}]
    existing = [{"build_start_time": "21:00", "template": _tmpl(480, 120), "push_mode": "sync", "strategy_name": "B"}]
    # 21:00 构建的占用区间 20:20~次日07:30，与 A 的 21:20 起重叠
    assert len(detect_conflicts("2026-08-08", cand, existing)) >= 1
```

- [ ] **Step 3: test_api.py — 登录/冲突/PM 归属/结论流转**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.seed.seed import seed

client = TestClient(app)

def _login(username="pm27a", password="123456"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["token"]

def test_login_and_me():
    token = _login("admin")
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["data"]["role"] == "admin"

def test_pm_cannot_edit_other_version():
    token = _login("pm27a")  # 27A PM
    # 尝试编辑 27B 分支策略（需先查到一个 27B 策略 id）
    r = client.get("/api/strategies", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # 构造一个属于其他版本分支的新策略请求
    r2 = client.post("/api/strategies", json={
        "branch_id": 3, "template_id": 1, "name": "越权", "build_start_time": "10:00",
        "push_mode": "normal", "enabled": True
    }, headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 403

def test_conclusion_duplicate_rejected():
    token = _login("tester")
    # 取一个 pending 轮次
    r = client.get("/api/executions", headers={"Authorization": f"Bearer {token}"})
    rounds = r.json()["data"]
    pending = next(x for x in rounds if x["conclusion"] == "pending")
    h = {"Authorization": f"Bearer {token}"}
    r1 = client.post(f"/api/executions/rounds/{pending['id']}/conclusion",
                     json={"conclusion": "pass", "note": "ok"}, headers=h)
    assert r1.status_code == 200
    r2 = client.post(f"/api/executions/rounds/{pending['id']}/conclusion",
                     json={"conclusion": "pass", "note": "again"}, headers=h)
    assert r2.status_code == 409
```

- [ ] **Step 4: 运行全部测试**

Run: `cd backend && .\.venv\Scripts\python -m pytest tests -v`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "test: 后端单元与接口测试"
```

---

## 前端任务（frontend/）

### Task F1: 前端基座初始化（pure-admin-thin）

**前置：** 后端 Task B1–B6 的契约已由设计文档固定，前端可独立进行。

**Files:**
- Run: 拉取 pure-admin-thin 到 `frontend/` 目录
- Create: `frontend/.env.development`（API 基址）
- Modify: `frontend/src/api/`（新增业务 API 模块）
- Modify: `frontend/src/router/routes.ts` / `asyncRoutes`（业务路由 + 角色权限）
- Modify: `frontend/src/store/modules/user.ts`（登录态对接后端）

- [ ] **Step 1: 拉取基座项目**

```bash
cd e:\GitHub\Hello-Build-Web
git clone --depth 1 https://gitee.com/yiming_chang/pure-admin-thin.git frontend
# 若 gitee 不可用回退 github：
# git clone --depth 1 https://github.com/pure-admin/pure-admin-thin.git frontend
cd frontend
npm install
```

> 注意：拉取后需删除 `frontend/.git` 使 frontend 成为工作区子目录（或用独立仓库，由主代理决定）。推荐 `Remove-Item frontend\.git -Recurse -Force`。

- [ ] **Step 2: 配置 API 基址 `.env.development`**

```
VITE_API_BASE_URL = http://localhost:8000/api
```

- [ ] **Step 3: 确认基座可运行**

Run: `cd frontend && npm run dev`
Expected: 打开 pure-admin 默认登录页/首页。

- [ ] **Step 4: 对接后端认证（src/api/auth.ts + user store）**

创建 `frontend/src/api/types.ts` 定义后端响应与实体类型（对齐设计文档 7.1 错误码与 7.2 接口）：

```ts
// src/api/types.ts
export interface ApiResponse<T> { code: number; message: string; data: T }
export interface UserInfo {
  id: number; username: string; display_name: string; role: string;
  bound_version_id?: number; bound_version_name?: string;
}
export interface LoginResult { token: string; user: UserInfo }
export interface TimelinePhase { start: string; end: string }
export interface Timeline { push: TimelinePhase | null; build: TimelinePhase; smoke: TimelinePhase; analysis: TimelinePhase }
export interface StrategyItem {
  id: number; branch_id: number; branch_name: string; version_id: number;
  template_id: number; template_name: string; name: string;
  build_start_time: string; push_mode: string; enabled: boolean;
}
export interface RoundItem {
  id: number; strategy_id: number; exec_date: string;
  push_start: string | null; push_end: string | null;
  build_start: string; build_end: string; smoke_start: string; smoke_end: string;
  analysis_start: string; analysis_end: string;
  conclusion: string; conclusion_note?: string; push_status: string; release_approved?: boolean;
}
```

创建 `frontend/src/api/http.ts`（Axios 封装，统一拦截 401/403/409）：

```ts
import axios from "axios"
import { ElMessage } from "element-plus"

const service = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL, timeout: 15000 })
service.interceptors.request.use((config) => {
  const token = localStorage.getItem("token")
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
service.interceptors.response.use(
  (res) => { const d = res.data; if (d.code !== 0) { ElMessage.error(d.message); return Promise.reject(d) } return d.data },
  (err) => {
    const d = err.response?.data?.detail
    const code = d?.code
    if (code === 40101) { localStorage.removeItem("token"); window.location.href = "/#/login" }
    else if (code === 40301) ElMessage.error("无权限执行该操作")
    else if (code === 40901) ElMessage.error(`策略时间冲突：${d.message}`)
    else if (code === 40902) ElMessage.error(d?.message || "结论已录入")
    else ElMessage.error(d?.message || "请求失败")
    return Promise.reject(err)
  }
)
export default service
```

> 说明：pure-admin-thin 自带 Axios 封装（src/utils/http.ts）与 user store。**建议优先复用基座自带的 request 封装**，仅在其上增加业务拦截（409 冲突弹框）。若基座封装不含 baseURL 配置，则新增上述 `http.ts`。由主代理在初始化时确认基座实际结构后决定。

- [ ] **Step 5: 配置角色动态路由（asyncRoutes）**

在 pure-admin 的角色路由配置中新增 6 个业务页面路由，设置 `meta.roles` 控制可见性：

| 路由 path | 对应页面 | 可见角色 |
|---|---|---|
| /plan | 版本计划甘特看板 | 全部 |
| /execution | 今日执行 | 全部 |
| /panorama | 策略全景 | 全部 |
| /strategy | 策略配置 | pm |
| /system | 系统管理 | admin |
| /logs | 日志中心 | 全部 |

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: 前端基座初始化与后端对接（API封装/路由/认证）"
```

### Task F2: 版本计划甘特看板

**Files:**
- Create: `frontend/src/views/plan/index.vue`
- Create: `frontend/src/components/gantt/GanttChart.vue`（可复用甘特组件）
- Create: `frontend/src/api/plan.ts`

设计文档 8.2。跨天连续时间轴（默认当日18:00→次日12:00）、纵轴版本→分支→策略、色块着色（蓝构建/紫冒烟/橙分析/绿推送，冲突红斜纹）、悬停详情、PM 点击跳转策略编辑、日期+版本/分支筛选。

- [ ] **Step 1: API 模块 plan.ts**

```ts
import http from "@/api/http"
export function getPlan(params: { date: string; version_id?: number; branch_id?: number }) {
  return http.get("/plan", { params })
}
```

- [ ] **Step 2: 甘特组件 GanttChart.vue**

实现要点：
- props：`data`（版本→分支→策略→timeline）、`rangeStart`（Date）、`rangeEnd`（Date）、`pixelsPerMinute`；
- 计算函数 `timeToX(t: string): number` = `(Date.parse(t) - Date.parse(rangeStart)) / 60000 * pixelsPerMinute`；
- 色块元素：`<div class="phase" :style="{left, width, background: color}">`，颜色映射 `{build:'#3b82f6', smoke:'#8b5cf6', analysis:'#f59e0b', push:'#10b981'}`；
- 冲突标记：若 strategies 带 `conflict` 标记则覆盖红色斜纹（`repeating-linear-gradient`）；
- 悬停：`@mouseenter` 显示 tooltip（阶段/起止时间/状态）；
- 跨天：时间轴从 `parse_build_start` 前 6h 到次日 +12h，色块用绝对时间定位，天然跨越零点。

```vue
<!-- GanttChart.vue 核心模板结构 -->
<template>
  <div class="gantt-wrap">
    <div class="gantt-scroll">
      <div class="gantt-body" :style="{ position: 'relative', height: rowHeight * data.length + 'px' }">
        <div v-for="(item, i) in rows" :key="item.id" class="gantt-row" :style="{ top: i * rowHeight + 'px' }">
          <div class="gantt-label">{{ item.label }}</div>
          <div class="gantt-track">
            <div v-for="p in item.phases" :key="p.key" class="phase"
                 :class="{ conflict: p.conflict }"
                 :style="{ left: timeToX(p.start) + 'px', width: Math.max(timeToX(p.end) - timeToX(p.start), 3) + 'px', background: colorOf(p.stage) }"
                 @mouseenter="showTip($event, p)"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 3: 看板页 plan/index.vue**

- 顶部：日期选择器 + 版本/分支筛选 + 图例（色块含义 + 冲突斜纹）；
- 调用 `getPlan({date})`，把返回的版本→分支→策略数据展开为 `rows`（label = 版本·分支·策略，phases = 各阶段绝对时间）；
- 版本行分组标题（含 PM 名），策略行缩进；
- PM 点击本版本策略行 → 跳转 `/strategy`（带策略 id）。

- [ ] **Step 4: 验证**

Run: `cd frontend && npm run dev`，登录后进入"版本计划"页，确认甘特渲染、跨天色块、筛选生效。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/plan frontend/src/components/gantt frontend/src/api/plan.ts
git commit -m "feat: 版本计划甘特看板"
```

### Task F3: 今日执行看板

**Files:**
- Create: `frontend/src/views/execution/index.vue`
- Create: `frontend/src/api/execution.ts`

设计文档 8.3。统计卡片（今日轮次/进行中/待录结论/推送成功）、轮次表格（构建/冒烟/人工分析/结论/推送五列状态）、结论录入弹窗（仅 tester）、PM 仅本版本、30s 轮询。

- [ ] **Step 1: API 模块 execution.ts**

```ts
import http from "@/api/http"
export function getExecutions(params: { date?: string; strategy_id?: number; from?: string; to?: string }) {
  return http.get("/executions", { params })
}
export function submitConclusion(roundId: number, data: { conclusion: string; note?: string }) {
  return http.post(`/executions/rounds/${roundId}/conclusion`, data)
}
```

- [ ] **Step 2: 看板页 execution/index.vue**

- 统计卡片：从 `getExecutions({date: today})` 计算结果（总数 / conclusion=pending 且进行中 / 待录结论 / push_status=success）；
- 表格列：策略名、构建、冒烟、人工分析、结论、推送（各列显示状态徽标：待执行/进行中/成功/失败/跳过）；
- 结论列：pending 显示「录入结论」按钮（仅 `role==='tester'`）；
- 结论弹窗：通过/不通过单选 + 备注 textarea → `submitConclusion` → 刷新 + 全局消息；
- 30s 定时器轮询刷新（`setInterval`，组件 `onUnmounted` 清理）；
- PM 角色：表格数据由后端已过滤本版本，前端仅展示。

- [ ] **Step 3: 验证 + Commit**

Run: `npm run dev`，以 tester 登录录入结论，验证正常模式推送状态流转、重复录入被拒。
```bash
git add frontend/src/views/execution frontend/src/api/execution.ts
git commit -m "feat: 今日执行看板"
```

### Task F4: 策略全景页

**Files:**
- Create: `frontend/src/views/panorama/index.vue`
- Create: `frontend/src/api/panorama.ts`（复用 strategies + executions）

设计文档 8.4。筛选栏（版本→分支级联→执行记录时间范围，默认近7天）；①策略配置全景区（策略卡片网格）；②执行实践全景区（点击卡片联动历史轮次倒序表格 + 行展开日志抽屉）。全角色只读，无编辑入口。

- [ ] **Step 1: API 模块 panorama.ts**

```ts
import http from "@/api/http"
export function getStrategies(params: { version_id?: number; branch_id?: number }) {
  return http.get("/strategies", { params })
}
export function getExecutions(params: { strategy_id?: number; from?: string; to?: string }) {
  return http.get("/executions", { params })
}
export function getRoundDetail(roundId: number) {
  return http.get(`/executions/rounds/${roundId}`)
}
```

- [ ] **Step 2: 全景页 panorama/index.vue**

- 筛选栏：版本下拉（全部/指定）→ 分支下拉（随版本级联，清空重载）→ 时间范围日期选择器（默认近7天）；
- 策略配置区：卡片网格，卡片含策略名/版本·分支/模板/构建开始时间/推送模式/启用状态；不筛选时按版本→分支分组；
- 联动：点击策略卡片 → 高亮选中 → 下方执行实践区 `getExecutions({strategy_id, from, to})` 倒序表格（日期×构建/冒烟/分析/结论/推送/备注）；
- 行点击 → `getRoundDetail` 展开日志抽屉（执行日志列表）；
- 整页无编辑按钮。

- [ ] **Step 3: 验证 + Commit**

```bash
git add frontend/src/views/panorama frontend/src/api/panorama.ts
git commit -m "feat: 策略全景页"
```

### Task F5: 策略配置页

**Files:**
- Create: `frontend/src/views/strategy/index.vue`
- Create: `frontend/src/api/strategy.ts`

设计文档 8.5。表单字段（模板/名称/构建开始时间/推送模式/启用开关）、底部时间线实时预览（编辑即调 preview 接口）、保存前二次确认、冲突不可保存。

- [ ] **Step 1: API 模块 strategy.ts**

```ts
import http from "@/api/http"
export function getStrategies(params?: { version_id?: number; branch_id?: number }) { return http.get("/strategies", { params }) }
export function previewStrategy(data: StrategyForm) { return http.post("/strategies/preview", data) }
export function createStrategy(data: StrategyForm) { return http.post("/strategies", data) }
export function updateStrategy(id: number, data: StrategyForm) { return http.patch(`/strategies/${id}`, data) }
export function toggleStrategy(id: number, enabled: boolean) { return http.patch(`/strategies/${id}/toggle`, null, { params: { enabled } }) }
```

> 说明：`toggleStrategy` 的 query 传参方式需匹配后端 `enabled: bool` 查询参数；若后端用 body 则改为 body。以后端为准（设计文档 PATCH /toggle 传 enabled）。

- [ ] **Step 2: 策略列表 + 表单**

- 上半区：本版本策略列表（表格/卡片，含启用开关直接 toggle）；
- 下半区：策略编辑表单（新建/编辑切换）：
  - 模板下拉（从 `/admin/templates` 或 `/strategies` 关联获取模板列表）；
  - 策略名称（默认自动生成：`{版本}-{分支}-{模板名}`，可改）；
  - 构建开始时间（`el-time-picker` 格式 HH:MM）；
  - 推送模式（`el-radio-group`: 正常流程推送 / 同步推送冒烟）；
  - 启用开关；
- 时间线实时预览：字段变化触发 `previewStrategy`，底部渲染各阶段条（复用甘特迷你展示）；
- 冲突时：预览区红色提示 + 冲突详情，保存按钮禁用；
- 保存：二次确认（`ElMessageBox.confirm`）→ create/update → 刷新列表 + 成功消息。

- [ ] **Step 3: 验证 + Commit**

```bash
git add frontend/src/views/strategy frontend/src/api/strategy.ts
git commit -m "feat: 策略配置页"
```

### Task F6: 系统管理页

**Files:**
- Create: `frontend/src/views/admin/index.vue`
- Create: `frontend/src/api/admin.ts`

设计文档 8.6。四个 Tab：版本分支（PM 绑定一对一）、用户管理、策略模板（被引用不可删）、关键配置。

- [ ] **Step 1: API 模块 admin.ts**

```ts
import http from "@/api/http"
export const adminApi = {
  getVersions: () => http.get("/admin/versions"),
  createVersion: (d: any) => http.post("/admin/versions", d),
  updateVersion: (id: number, d: any) => http.patch(`/admin/versions/${id}`, d),
  addBranch: (vid: number, branchName: string) => http.post(`/admin/versions/${vid}/branches`, null, { params: { branch_name: branchName } }),
  getUsers: () => http.get("/admin/users"),
  createUser: (d: any) => http.post("/admin/users", d),
  updateUser: (id: number, d: any) => http.patch(`/admin/users/${id}`, d),
  getTemplates: () => http.get("/admin/templates"),
  createTemplate: (d: any) => http.post("/admin/templates", d),
  updateTemplate: (id: number, d: any) => http.patch(`/admin/templates/${id}`, d),
  deleteTemplate: (id: number) => http.delete(`/admin/templates/${id}`),
  getConfig: () => http.get("/admin/config"),
  updateConfig: (d: any) => http.put("/admin/config", d),
}
```

- [ ] **Step 2: 页面 admin/index.vue**

- Tab1 版本分支：版本表格（名称/PM/状态）+ 分支子表；PM 绑定下拉仅显示未绑定版本的 pm 角色用户（需后端提供候选用户接口或前端过滤 users 列表）；新增/编辑版本弹窗；
- Tab2 用户管理：用户表格 + 新建/编辑/启停/重置密码弹窗；
- Tab3 策略模板：模板表格（名称/冒烟耗时/分析耗时）+ 新增/编辑/删除；删除被引用模板时后端返回 422 提示；
- Tab4 关键配置：构建耗时/推送耗时/同步缓冲三个数字输入 → 保存。

> 说明：PM 绑定候选用户若后端无专门接口，可在 Tab1 中调用 `adminApi.getUsers()` 后前端过滤 `role==='pm'` 且 `未绑定`。

- [ ] **Step 3: 验证 + Commit**

```bash
git add frontend/src/views/admin frontend/src/api/admin.ts
git commit -m "feat: 系统管理页"
```

### Task F7: 日志中心

**Files:**
- Create: `frontend/src/views/logs/index.vue`
- Create: `frontend/src/api/logs.ts`

设计文档 8.7。Tab：执行日志·变更日志·管理操作（仅管理员）·登录安全（仅管理员）。统一表格 + 时间范围筛选。

- [ ] **Step 1: API 模块 logs.ts**

```ts
import http from "@/api/http"
export const logsApi = {
  execution: (p: any) => http.get("/logs/execution", { params: p }),
  changes: (p: any) => http.get("/logs/changes", { params: p }),
  operations: (p: any) => http.get("/logs/admin/operations", { params: p }),
  security: (p: any) => http.get("/logs/admin/security", { params: p }),
}
```

- [ ] **Step 2: 页面 logs/index.vue**

- Tab 执行日志：日期/版本/分支筛选 + 表格（阶段/事件/详情/时间）；
- Tab 变更日志：时间范围筛选 + 表格（谁/何时/策略字段 from→to）；
- Tab 管理操作（仅 admin 渲染）：操作/目标/详情/时间；
- Tab 登录安全（仅 admin 渲染）：事件/用户/时间；
- 统一表格组件 + 时间范围日期选择器。

- [ ] **Step 3: 验证 + Commit**

```bash
git add frontend/src/views/logs frontend/src/api/logs.ts
git commit -m "feat: 日志中心"
```

---

## 验收标准（全流程演示脚本）

以五角色走查（设计文档第十章端到端演示）：
1. **admin** 登录 → 系统管理查看/编辑版本、用户、模板、关键配置；
2. **pm27a** 登录 → 版本计划（只读全局）→ 策略配置（仅 27A 分支）→ 新建/编辑策略（preview 冲突检测）→ 保存；
3. **builder** 登录 → 版本计划 + 今日执行查看推送状态；
4. **tester** 登录 → 今日执行 → 录入结论（pass/fail）→ 正常模式触发推送（mock 留痕）、同步模式写 release_approved；
5. **integrator** 登录 → 查看推送/集成状态；
6. **策略全景**：任意角色查看，版本/分支筛选 + 策略↔执行联动；
7. **日志中心**：查看执行/变更日志；admin 可看管理操作/登录安全。

---

## 并行执行编排

由于后端与前端为两个无共享代码的独立子系统，采用**并行 agent 派发**：

**并行组 1（后端链路，单 agent 顺序执行 B1→B7）：**
- 由主代理派发一个 GeneralPurpose agent 执行后端全部任务（B1–B7），因其内部有强依赖（模型→服务→API→联动），顺序执行更稳。

**并行组 2（前端链路，单 agent 顺序执行 F1→F7）：**
- 由主代理派发另一个 GeneralPurpose agent 执行前端全部任务（F1–F7），含基座拉取与 npm install。

**主代理职责：**
- 并行派发两个 agent，各自负责一个子系统；
- 两个 agent 完成后，主代理集成验证：启动后端 + 前端，跑全流程演示脚本；
- 处理跨端契约对齐问题（若前端 agent 发现后端字段不符，主代理协调修正）。

> 说明：为保证契约一致，两个 agent **必须**以设计文档 `docs/superpowers/specs/2026-08-08-build-strategy-web-design.md` 为唯一契约基准，前后端字段命名严格对齐设计文档 7.2 接口清单。

## 假设与风险

| 假设/风险 | 处置 |
|---|---|
| pure-admin-thin 基座结构（路由/请求封装/目录）与本文预设略有差异 | 前端 agent 以基座实际结构为准适配，保持"6 页面 + 角色路由 + 后端对接"目标不变 |
| Python 3.14 下 passlib/bcrypt 兼容性 | 若不兼容，改用 `bcrypt` 直接或 `pwdlib`；由后端 agent 处理并记录 |
| 前后端契约字段 | 以后端 OpenAPI（/docs）与设计文档为准，前端按契约消费 |