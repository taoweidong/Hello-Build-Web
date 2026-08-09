import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import AnyUrl, BeforeValidator, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # 从 backend/.env 加载本地开发配置
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )
    # 对外 API 前缀（前端已依赖 /api，保持不变）
    API_V1_STR: str = "/api"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    FRONTEND_HOST: str = "http://localhost:8848"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str = "构建策略配置系统"

    # 数据库连接串：默认本地 SQLite，部署时可切换为 postgresql+psycopg://...
    DATABASE_URL: str = "sqlite:///./build_strategy.db"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return self.DATABASE_URL

    # 初始数据：首位管理员（initial_data 写入）
    FIRST_SUPERUSER: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str = "123456"

    # 全局构建参数默认值（管理员可通过 /api/admin/config 运行时调整）
    BUILD_MINUTES: int = 30
    PUSH_MINUTES: int = 20
    SYNC_BUFFER_MINUTES: int = 20

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self):
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def build_minutes(self) -> int:
        return self.BUILD_MINUTES

    @computed_field  # type: ignore[prop-decorator]
    @property
    def push_minutes(self) -> int:
        return self.PUSH_MINUTES

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_buffer_minutes(self) -> int:
        return self.SYNC_BUFFER_MINUTES


settings = Settings()  # type: ignore
