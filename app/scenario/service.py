"""가상 시나리오 (위험 단계 시연용). 실데이터에 3단계가 없어서, 한 장소의 검색량을 키우고
'검색 증가 = 방문 증가' 가정으로 같은 모델·판정 규칙을 돌려 봄.
결과는 DB(daily_results·daily_runs)에 넣지 않고 Redis에만 둠 → 실데이터 판정 이력·알림과 안 섞임"""
import json
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException

from app.core.cache import LOCK_KEY, r
from app.core.config import KST, settings
from app.core.db import SessionLocal
from app.judge import runtime
from app.judge.models import DailyResult
from app.places.models import Place

KEY = "miribom:scenario:{}"
TTL = 60 * 60 * 24 * 60   # 60일
LABEL = "가상 시나리오 · 실제 데이터 아님"


def key_of(judge_day: date, place_id: str, multiplier: float) -> str:
    return f"{judge_day}_{place_id}_x{multiplier:g}"


def info(payload: dict, place: Place, key: str) -> dict:
    sc = payload.get("가상 시나리오") or {}
    from miribom_ai.pipeline.run_daily import SCENARIO_ASSUME
    return {"key": key, "label": LABEL, "place_id": place.id, "place": place.name,
            "multiplier": sc.get("multiplier"), "start": sc.get("start"), "assumption": SCENARIO_ASSUME}


def run(judge_day: date, place_id: str, multiplier: float, start: date | None) -> str:
    """시나리오를 돌려 Redis에 저장하고 키를 돌려줌. 재현처럼 판정일 07시 전 별칭만 씀"""
    import miribom_ai
    with SessionLocal() as s:
        place = s.get(Place, place_id)
        if not place:
            raise HTTPException(404, "없는 장소")
        if not r.set(LOCK_KEY, "1", nx=True, ex=1800):
            raise HTTPException(409, "판정 작업이 이미 실행 중임. 잠시 뒤 다시 시도할 것")
        try:
            runtime.write_places(s, alias_before=datetime.combine(judge_day, time(7), KST))
            start = start or judge_day - timedelta(days=3)
            payload = miribom_ai.run_daily(str(judge_day), demo=settings.miribom_demo, save=False,
                                           scenario={"place": place.name, "multiplier": multiplier,
                                                     "start": str(start)})
        finally:
            r.delete(LOCK_KEY)
        key = key_of(judge_day, place_id, multiplier)
        r.set(KEY.format(key), json.dumps({"payload": payload, "info": info(payload, place, key)},
                                          ensure_ascii=False), ex=TTL)
        return key


def load(key: str) -> DailyResult:
    """저장된 시나리오를 판정 결과 모양으로 (DB에 넣지 않는 임시 객체). row.scenario로 구분"""
    raw = r.get(KEY.format(key))
    if not raw:
        raise HTTPException(404, "그 가상 시나리오 결과가 없음. POST /api/admin/scenario 로 먼저 돌릴 것")
    d = json.loads(raw)
    row = DailyResult(judge_day=date.fromisoformat(d["payload"]["판정일"]), demo=False, replay=True,
                      payload=d["payload"])
    row.scenario = d["info"]
    return row
