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

    # miribom-ai 레포 위치 (모델·자료). 서버는 MIRIBOM_HOME(작업 폴더)에 places.csv를 새로 쓰고 models/data는 여기로 연결함
    miribom_ai_dir: str = "/opt/miribom-ai"
    miribom_home: str = "/srv/runtime"

    # 로그인 토큰
    jwt_secret: str = "dev-only-change-me"
    jwt_hours: int = 12
    # 시연용 계정 비밀번호 (처음 실행 때 계정 생성)
    seed_password: str = "miribom1234"

    # 수동 실행 API를 로그인 없이 부를 때 쓰는 토큰 (비우면 꺼짐)
    admin_token: str = ""

    # Threads 앱 ID·시크릿 (로그인, 연결 해제·삭제 콜백 서명 확인). 대시보드의 Threads 앱 ID를 씀 (페이스북 앱 ID와 다름)
    threads_app_id: str = ""
    threads_app_secret: str = ""
    public_base_url: str = "http://localhost:8000"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
