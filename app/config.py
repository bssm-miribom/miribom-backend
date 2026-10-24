"""환경변수 설정. 값은 루트 .env에서 읽음 (docker-compose가 넣어줌)"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://miribom:miribom@db:5432/miribom"
    redis_url: str = "redis://redis:6379/0"
    cors_origins: str = "http://localhost:8081,http://localhost:19006"

    # 매일 판정 예약 (한국시간)
    scheduler_enabled: bool = True
    daily_hour: int = 6
    daily_minute: int = 0
    # true면 네이버 키·학습 모델 없이 가짜 데이터로 판정 (개발용)
    miribom_demo: bool = True

    # 수동 실행 API(/api/admin/run) 보호용
    admin_token: str = ""

    # Threads 앱 시크릿 (연결 해제·삭제 콜백 서명 확인)
    threads_app_secret: str = ""
    public_base_url: str = "http://localhost:8000"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
