"""시간대별 혼잡 (오전·점심·오후·저녁). 비율 표는 scripts/build_time_profile.py가 도시철도 시간대별 하차 실측으로 만듦

한 시간대 밀집도 = 그날 밀집도(예측 중앙값·상단) × peak_ratio
  peak_ratio = 그 시간대 가장 붐빈 1시간 ÷ 09-22시 중 가장 붐빈 1시간 (휴일·평일 따로)
  → 가장 붐비는 시간대는 날짜별 혼잡과 같고, 나머지는 그 비율만큼 낮아짐. 혼잡 단계 기준은 날짜별과 같음 (1㎡당 5명)
"""
import json
import math
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import holidays

from app.dashboard.views import CROWD_LABEL, LIMIT, by_name, forecasts, stage_of
from app.judge.models import DailyResult
from app.places.models import Place

PROFILE = Path(__file__).with_name("time_profile.json")
RANK = {"free": 0, "normal": 1, "busy": 2, "very_busy": 3}


@lru_cache
def profile() -> dict:
    return json.loads(PROFILE.read_text(encoding="utf-8"))


def is_rest(d: date) -> bool:
    return d.weekday() >= 5 or d in holidays.KR(years=d.year)


def _crowd(stage: str, density: float | None, density_high: float | None) -> str | None:
    if stage == "normal":
        return "free"
    if stage == "failed":
        return None
    if (density or 0) > LIMIT:
        return "very_busy"
    if (density_high or 0) > LIMIT:
        return "busy"
    return "normal"


def least_slot(slots: list[dict]) -> str | None:
    ok = [x for x in slots if x["crowd"] in RANK]
    if len({x["crowd"] for x in ok}) < 2:
        return None
    return min(ok, key=lambda x: (RANK[x["crowd"]], x["share"]))["slot"]


def time_slots(row: DailyResult | None, place: Place) -> dict:
    prof = profile()
    pp = prof["places"].get(place.name)
    method = {"source": prof["source"], "period": prof["period"], "stations": pp["stations"] if pp else None,
              "note": "도시철도 하차 실측 비율로 나눈 추정치. 역 하차에는 통근·환승 이용객도 섞임"}
    if row is None or pp is None:
        return {"days": [], "method": method, "available": pp is not None}
    p = by_name(row.payload).get(place.name)
    stage, fc = stage_of(p), {f["date"]: f for f in forecasts(p or {})}
    days = []
    dates = list(fc) or [str(row.judge_day + timedelta(days=h)) for h in (1, 2, 3)]
    for d in dates:
        f = fc.get(d, {})
        kind = "rest" if is_rest(date.fromisoformat(d)) else "work"
        slots = []
        for key, meta in prof["slots"].items():
            v = pp[kind]["slots"][key]
            r = v["peak_ratio"]
            dm = None if f.get("density_mid") is None else round(f["density_mid"] * r, 2)
            dh = None if f.get("density_high") is None else round(f["density_high"] * r, 2)
            c = _crowd(stage, dm, dh)
            slots.append({"slot": key, "label": meta["label"], "start": meta["start"], "end": meta["end"],
                          "share": v["share"], "crowd": c, "crowd_label": CROWD_LABEL[c]})
        days.append({"date": d, "day_type": kind, "slots": slots, "least_crowded_slot": least_slot(slots)})
    return {"days": days, "method": method, "available": True}


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """두 점 사이 거리(m), 하버사인"""
    R = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return round(2 * R * math.asin(math.sqrt(a)))
