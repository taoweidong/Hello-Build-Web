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