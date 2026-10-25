"""저장된 판정 결과(run_daily dict)를 화면용 응답으로 바꿈"""
import json
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import LATEST_KEY, r
from app.db import Account, Alias, DailyResult, Place
from app.jobs import KST

LIMIT = 5.0   # 1㎡당 5명 (miribom_ai.alert.judge.LIMIT와 같음)
STAGE = {"평상": "normal", "1단계": "stage1", "2단계": "stage2", "3단계": "stage3",
         "판정 보류": "pending", "수집 실패": "failed"}
ORDER = {"stage3": 0, "stage2": 1, "stage1": 2, "pending": 3, "failed": 4, "normal": 5}
CROWD_LABEL = {"free": "여유", "normal": "보통", "busy": "붐빔", "very_busy": "매우 붐빔", None: "예보 준비 중"}
DISCLAIMER = "예측에 기반한 추정치이며 실제와 다를 수 있음 · 매일 07시 갱신"


# ===== 판정 결과 찾기 =====
def find_result(s: Session, judge_day: date | None = None, replay: bool = False) -> DailyResult | None:
    if judge_day is None and not replay:
        cached = r.get(LATEST_KEY)
        if cached:
            row = s.get(DailyResult, json.loads(cached)["id"])
            if row:
                return row
    q = select(DailyResult).where(DailyResult.replay == replay)
    if judge_day is not None:
        q = q.where(DailyResult.judge_day == judge_day)
    return s.scalars(q.order_by(DailyResult.judge_day.desc(), DailyResult.created_at.desc()).limit(1)).first()


def results_between(s: Session, row: DailyResult, days: int) -> list[DailyResult]:
    """row 판정일 기준 최근 days일의 같은 모드(운영·재현, demo) 결과. 날짜마다 가장 최근 것"""
    start = row.judge_day - timedelta(days=days - 1)
    rows = s.scalars(select(DailyResult).where(DailyResult.replay == row.replay, DailyResult.demo == row.demo,
                                                DailyResult.judge_day >= start, DailyResult.judge_day <= row.judge_day)
                     .order_by(DailyResult.created_at)).all()
    return list({x.judge_day: x for x in rows}.values())


def meta(row: DailyResult) -> dict:
    today = datetime.now(KST).date()
    return {"judge_day": str(row.judge_day), "generated_at": row.payload.get("생성 시각"), "demo": row.demo,
            "replay": row.replay, "stale": (not row.replay and not row.demo and row.judge_day < today)}


def by_name(payload: dict) -> dict[str, dict]:
    return {p["장소"]: p for p in payload.get("장소", [])}


# ===== 장소 한 곳 =====
def forecasts(p: dict) -> list[dict]:
    dens = p.get("밀집도") or {}
    out = []
    for h, v in sorted((p.get("예측") or {}).items(), key=lambda kv: int(kv[0])):
        d = dens.get(v["날짜"]) or {}
        out.append({"horizon": int(h), "date": v["날짜"], "low": v["하위10"], "mid": v["중앙값"], "high": v["상위90"],
                    "density_mid": d.get("중앙값"), "density_high": d.get("상위90")})
    return out


def stage_of(p: dict | None) -> str:
    return STAGE.get((p or {}).get("단계"), "failed" if p else "normal")


def place_row(place: Place, p: dict | None, prev: dict | None, new_aliases: list[str]) -> dict:
    stage, reason = stage_of(p), (p or {}).get("이유")
    if new_aliases and stage == "normal":   # A-06: 별칭 등록 즉시 1단계로 보여줌
        stage, reason = "stage1", f"신규 별칭 '{new_aliases[0]}' 등록 · 다음 판정부터 반영"
    fc = forecasts(p or {})
    return {"id": place.id, "name": place.name, "district": place.district, "lat": place.lat, "lon": place.lon,
            "stage": stage, "surge_ratio": ((p or {}).get("급증") or {}).get("오늘 배수"), "intent_posts": None,
            "d1": fc[0] if fc else None, "bottleneck_name": place.bottleneck_name,
            "is_new": bool(new_aliases) or (stage != "normal" and stage_of(prev) == "normal"),
            "new_alias": new_aliases[0] if new_aliases else None, "reason": reason}


def aliases_after(s: Session, row: DailyResult) -> dict[str, list[str]]:
    """판정 결과가 만들어진 뒤 등록된 별칭 (재현 결과에는 안 붙임)"""
    if row.replay:
        return {}
    out: dict[str, list[str]] = {}
    for a in s.scalars(select(Alias).where(Alias.created_at > row.created_at).order_by(Alias.created_at)):
        out.setdefault(a.place_id, []).append(a.alias)
    return out


# ===== 관리자 =====
def dashboard(s: Session, row: DailyResult, acc: Account) -> dict:
    now = by_name(row.payload)
    prev_row = s.scalars(select(DailyResult).where(DailyResult.replay == row.replay, DailyResult.demo == row.demo,
                                                    DailyResult.judge_day == row.judge_day - timedelta(days=1))
                         .order_by(DailyResult.created_at.desc()).limit(1)).first()
    prev = by_name(prev_row.payload) if prev_row else {}
    new_alias = aliases_after(s, row)
    from app.auth import can_see
    rows = [place_row(pl, now.get(pl.name), prev.get(pl.name) if prev_row else None, new_alias.get(pl.id, []))
            for pl in s.scalars(select(Place)) if can_see(acc, pl)]
    # 전날 판정이 없으면 '신규'를 판단할 수 없어서 별칭 신규만 남김
    if not prev_row:
        for x in rows:
            x["is_new"] = x["new_alias"] is not None
    rows = [x for x in rows if x["stage"] != "normal"]
    rows.sort(key=lambda x: (ORDER[x["stage"]], -(x["surge_ratio"] or 0)))
    summary = {k: sum(x["stage"] == k for x in rows) for k in ("stage3", "stage2", "stage1", "pending")}
    return {"meta": meta(row), "summary": summary, "places": rows}


def place_detail(s: Session, row: DailyResult, place: Place) -> dict:
    p = by_name(row.payload).get(place.name)
    new_alias = aliases_after(s, row).get(place.id, [])
    base = place_row(place, p, None, new_alias)
    trend = []
    for x in results_between(s, row, 7):
        ratio = ((by_name(x.payload).get(place.name) or {}).get("급증") or {}).get("오늘 배수")
        trend.append({"date": str(x.judge_day - timedelta(days=1)), "surge_ratio": ratio})   # 배수는 D-1 자료
    surge = (p or {}).get("급증") or {}
    ok = all(v is not None for v in (place.bottleneck_m2, place.peak_share, place.bottleneck_share))
    return {"meta": meta(row),
            "place": {"id": place.id, "name": place.name, "district": place.district,
                      "aliases": [a.alias for a in s.scalars(select(Alias).where(Alias.place_id == place.id))]},
            "stage": base["stage"], "reason": base["reason"],
            "surge": {"ratio": surge.get("오늘 배수"), "top1pct": surge.get("상위 기준"),
                      "year_max": surge.get("1년 최대"), "reason": surge.get("이유")},
            "trend": trend, "actual_visitors": [], "forecasts": forecasts(p or {}),
            "bottleneck": {"name": place.bottleneck_name, "area_m2": place.bottleneck_m2, "limit_per_m2": LIMIT,
                           "limit_visitors": round(LIMIT * place.bottleneck_m2 / (place.peak_share * place.bottleneck_share))
                           if ok else None, "estimated": True},
            "weather_source": (p or {}).get("날씨 출처")}


# ===== 시민 =====
def crowd_days(row: DailyResult | None, place: Place) -> list[dict]:
    """경보 단계 → 시민 혼잡 4단계 (날짜별) [팀 확인]"""
    if row is None:
        return []
    p = by_name(row.payload).get(place.name)
    stage, fc = stage_of(p), forecasts(p or {})
    dates = [f["date"] for f in fc] or [str(row.judge_day + timedelta(days=h)) for h in (1, 2, 3)]
    out = []
    for i, d in enumerate(dates):
        f = fc[i] if i < len(fc) else {}
        if stage == "normal":
            c = "free"
        elif stage == "failed":
            c = None
        elif (f.get("density_mid") or 0) > LIMIT:
            c = "very_busy"
        elif (f.get("density_high") or 0) > LIMIT:
            c = "busy"
        else:
            c = "normal"
        out.append({"date": d, "crowd": c, "label": CROWD_LABEL[c]})
    return out


def least_crowded(days: list[dict]) -> str | None:
    rank = {"free": 0, "normal": 1, "busy": 2, "very_busy": 3}
    ok = [d for d in days if d["crowd"] in rank]
    if len({d["crowd"] for d in ok}) < 2:   # 다 같으면 추천할 날이 없음
        return None
    return min(ok, key=lambda d: rank[d["crowd"]])["date"]
