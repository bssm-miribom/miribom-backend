"""테스트: SQLite + 가짜 Redis + miribom_ai 가짜 데이터 모드(demo). 네이버 키·Postgres 없이 돌아감

  pip install -r requirements.txt -r requirements-dev.txt -e ../miribom-ai
  pytest
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AI_DIR = Path(os.environ.get("MIRIBOM_AI_DIR_TEST", ROOT.parent / "miribom-ai"))
TMP = Path(tempfile.mkdtemp(prefix="miribom-test-"))
os.environ.update(DATABASE_URL=f"sqlite:///{TMP / 'test.db'}", MIRIBOM_AI_DIR=str(AI_DIR),
                  MIRIBOM_HOME=str(TMP / "runtime"), SCHEDULER_ENABLED="false", MIRIBOM_DEMO="true",
                  ADMIN_TOKEN="test-token", SEED_PASSWORD="pw")
sys.path.insert(0, str(ROOT))

import fakeredis  # noqa: E402

from app.core import cache  # noqa: E402

cache.r = fakeredis.FakeRedis(decode_responses=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def login(client, username):
    res = client.post("/api/auth/login", json={"username": username, "password": "pw"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture(scope="session")
def city(client):
    return login(client, "busan")


@pytest.fixture(scope="session")
def donggu(client):
    return login(client, "donggu")


@pytest.fixture(scope="session")
def police(client):
    return login(client, "police_dong")


@pytest.fixture(scope="session")
def judged(client, city):
    """가짜 데이터로 2026-09-20 판정을 한 번 돌림 (북항친수공원만 급증)"""
    res = client.post("/api/admin/run", headers=city)
    assert res.status_code == 200, res.text
    return res.json()
