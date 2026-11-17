"""DB 연결과 테이블 기반 클래스. 테이블은 기능 폴더마다 models.py에 있음"""
from sqlalchemy import JSON, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
JSONType = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


def load_models():
    """모든 기능의 테이블을 Base에 등록 (create_all 전에 불러야 함)"""
    import app.auth.models  # noqa: F401
    import app.judge.models  # noqa: F401
    import app.notices.models  # noqa: F401
    import app.places.models  # noqa: F401
    import app.response.models  # noqa: F401
    import app.threads.models  # noqa: F401


def init_db():
    # 지금은 시작할 때 테이블만 만듦. 스키마가 자주 바뀌면 Alembic으로 옮김
    load_models()
    Base.metadata.create_all(engine)
    if engine.dialect.name != "postgresql":   # 테스트(SQLite)는 새로 만들어서 필요 없음
        return
    with engine.begin() as c:   # 예전 DB에 없던 칸
        c.execute(text("ALTER TABLE daily_results ADD COLUMN IF NOT EXISTS replay boolean NOT NULL DEFAULT false"))
        c.execute(text("ALTER TABLE places ADD COLUMN IF NOT EXISTS bottleneck_polygon jsonb"))



def get_session():
    with SessionLocal() as s:
        yield s
