"""저장된 판정 결과(run_daily dict)를 화면용 응답으로 바꿈"""
import json
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import LATEST_KEY, r
from app.core.config import KST, settings
from app.auth.models import Account
from app.judge.models import DailyResult
from app.places.models import Alias, Place
from app.response.models import Checklist, Response, VisitorReport

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
    now = datetime.now(KST)
    # 오늘 판정은 06시에 돌고 몇십 초~몇 분 걸리므로, 07시가 지났는데도 오늘 결과가 없을 때만 '지연'으로 봄
    due = now.replace(hour=settings.daily_hour, minute=settings.daily_minute, second=0, microsecond=0) + timedelta(hours=1)
    expected = now.date() if now >= due else now.date() - timedelta(days=1)
    return {"judge_day": str(row.judge_day), "generated_at": row.payload.get("생성 시각"), "demo": row.demo,
            "replay": row.replay, "stale": (not row.replay and not row.demo and row.judge_day < expected)}


def by_name(payload: dict) -> dict[str, dict]:
    return {p["장소"]: p for p in payload.get("장소", [])}


# ===== 장소 한 곳 =====
def forecasts(p: dict) -> list[dict]:
    dens = p.get("밀집도") or {}
    out = []
    for h, v in sorted((p.get("예측") or {}).items(), key=lambda kv: int(kv[0])):
        d = dens.get(v["날짜"]) or {}
        out.append({"horizon": int(h), "date": v["날짜"], "low": v["하위10"], "mid": v["중앙값"], "high": v["상위90"],
                    "density_mid": d.get("중앙값"), "density_high": d.get("상위90"),
                    "worst": v.get("최악"), "density_worst": d.get("최악")})
    return out


def stage_of(p: dict | None) -> str:
    return STAGE.get((p or {}).get("단계"), "failed" if p else "normal")


def intent_of(p: dict | None) -> dict:
    """방문 의도 글 수 (Threads 수집·분류 결과가 있을 때만)"""
    i = (p or {}).get("의도") or {}
    return {"posts": i.get("어제 글 수"), "ratio": i.get("평소 대비")}


def place_row(place: Place, p: dict | None, prev: dict | None, new_aliases: list[str],
              response_level: str | None = None) -> dict:
    stage, reason = stage_of(p), (p or {}).get("이유")
    if new_aliases and stage == "normal":   # A-06: 별칭 등록 즉시 1단계로 보여줌
        stage, reason = "stage1", f"신규 별칭 '{new_aliases[0]}' 등록 · 다음 판정부터 반영"
    fc = forecasts(p or {})
    intent = intent_of(p)
    return {"id": place.id, "name": place.name, "district": place.district, "lat": place.lat, "lon": place.lon,
            "stage": stage, "surge_ratio": ((p or {}).get("급증") or {}).get("오늘 배수"),
            "intent_posts": intent["posts"], "intent_ratio": intent["ratio"],
            "d1": fc[0] if fc else None, "bottleneck_name": place.bottleneck_name,
            "is_new": bool(new_aliases) or (stage != "normal" and stage_of(prev) == "normal"),
            "new_alias": new_aliases[0] if new_aliases else None, "reason": reason,
            "worst_case": (p or {}).get("최악 시나리오"),
            "missing": (p or {}).get("빠진 값") or [], "response_level": response_level}


def response_levels(s: Session, judge_day) -> dict[str, str]:
    """판정일별 장소의 마지막 대응 수준 (A-11)"""
    rows = s.scalars(select(Response).where(Response.judge_day == judge_day).order_by(Response.decided_at)).all()
    return {r.place_id: r.level for r in rows}


def aliases_after(s: Session, row: DailyResult) -> dict[str, list[str]]:
    """판정 결과가 만들어진 뒤 등록된 별칭 (재현 결과에는 안 붙임)"""
    if row.replay:
        return {}
    out: dict[str, list[str]] = {}
    for a in s.scalars(select(Alias).where(Alias.created_at > row.created_at).order_by(Alias.created_at)):
        out.setdefault(a.place_id, []).append(a.alias)
    return out


# ===== 관리자 =====
def _rows(s: Session, row: DailyResult, acc: Account) -> list[dict]:
    """계정 관할 안의 급상승 후보 행 (normal 제외). 단계 높은 순 → 급증 배수 높은 순"""
    now = by_name(row.payload)
    prev_row = s.scalars(select(DailyResult).where(DailyResult.replay == row.replay, DailyResult.demo == row.demo,
                                                    DailyResult.judge_day == row.judge_day - timedelta(days=1))
                         .order_by(DailyResult.created_at.desc()).limit(1)).first()
    prev = by_name(prev_row.payload) if prev_row else {}
    new_alias = aliases_after(s, row)
    levels = {} if row.replay else response_levels(s, row.judge_day)
    from app.auth.service import can_see
    rows = [place_row(pl, now.get(pl.name), prev.get(pl.name) if prev_row else None, new_alias.get(pl.id, []),
                      levels.get(pl.id))
            for pl in s.scalars(select(Place)) if can_see(acc, pl)]
    # 전날 판정이 없으면 '신규'를 판단할 수 없어서 별칭 신규만 남김
    if not prev_row:
        for x in rows:
            x["is_new"] = x["new_alias"] is not None
    rows = [x for x in rows if x["stage"] != "normal"]
    rows.sort(key=lambda x: (ORDER[x["stage"]], -(x["surge_ratio"] or 0)))
    return rows


def dashboard(s: Session, row: DailyResult, acc: Account) -> dict:
    rows = _rows(s, row, acc)
    summary = {k: sum(x["stage"] == k for x in rows) for k in ("stage3", "stage2", "stage1", "pending")}
    return {"meta": meta(row), "summary": summary, "places": rows}


RISING = ("stage3", "stage2")   # A2 급상승 장소 목록에 띄우는 단계
STAGE_LABEL = {"stage3": "3단계 대응 필요", "stage2": "2단계 사전 대비"}


def rising(s: Session, row: DailyResult, acc: Account, stage: str | None = None) -> dict:
    """A-03 급상승 장소 목록: 3단계·2단계만. stage를 주면 그 단계만 (요약 줄 단계 누름 필터)"""
    rows = [x for x in _rows(s, row, acc) if x["stage"] in RISING]
    summary = {k: sum(x["stage"] == k for x in rows) for k in RISING}
    if stage:
        rows = [x for x in rows if x["stage"] == stage]
    return {"meta": meta(row), "summary": summary,
            "places": [{**x, "stage_label": STAGE_LABEL[x["stage"]]} for x in rows]}


def place_detail(s: Session, row: DailyResult, place: Place) -> dict:
    p = by_name(row.payload).get(place.name)
    new_alias = aliases_after(s, row).get(place.id, [])
    level = None if row.replay else response_levels(s, row.judge_day).get(place.id)
    base = place_row(place, p, None, new_alias, level)
    trend = []
    for x in results_between(s, row, 7):
        px = by_name(x.payload).get(place.name) or {}
        trend.append({"date": str(x.judge_day - timedelta(days=1)),   # 배수·글 수는 D-1 자료
                      "surge_ratio": (px.get("급증") or {}).get("오늘 배수"), "intent_posts": intent_of(px)["posts"]})
    # 실측 회신은 판정일 전날까지만 보여줌 (재현 화면에 미래 정보가 섞이지 않게)
    visits = s.scalars(select(VisitorReport).where(VisitorReport.place_id == place.id,
                                                   VisitorReport.date < row.judge_day,
                                                   VisitorReport.date >= row.judge_day - timedelta(days=30))
                       .order_by(VisitorReport.date)).all()
    cl = s.scalars(select(Checklist).where(Checklist.place_id == place.id, Checklist.judge_day == row.judge_day)
                   .order_by(Checklist.created_at.desc())).first()
    surge = (p or {}).get("급증") or {}
    return {"meta": meta(row),
            "place": {"id": place.id, "name": place.name, "district": place.district,
                      "aliases": [a.alias for a in s.scalars(select(Alias).where(Alias.place_id == place.id))]},
            "stage": base["stage"], "reason": base["reason"], "worst_case": base["worst_case"],
            "missing": base["missing"], "response_level": base["response_level"],
            "intent": {**intent_of(p), "model": "kcelectra" if intent_of(p)["posts"] is not None else None},
            "surge": {"ratio": surge.get("오늘 배수"), "top1pct": surge.get("상위 기준"),
                      "year_max": surge.get("1년 최대"), "reason": surge.get("이유")},
            "trend": trend, "forecasts": forecasts(p or {}),
            "actual_visitors": [{"date": str(v.date), "visitors": v.visitors, "source": v.source, "org": v.org}
                                for v in visits],
            "bottleneck": bottleneck_out(place),
            "weather_source": (p or {}).get("날씨 출처"),
            "checklist": ({"id": cl.id, "done": sum(i["done"] for i in cl.items), "total": len(cl.items)}
                          if cl else None)}


def limit_visitors(place: Place) -> int | None:
    """병목 기준(1㎡당 5명)을 하루 방문객으로 바꾼 값. 값이 하나라도 없으면 None"""
    if not all(v for v in (place.bottleneck_m2, place.peak_share, place.bottleneck_share)):
        return None
    return round(LIMIT * place.bottleneck_m2 / (place.peak_share * place.bottleneck_share))


def bottleneck_out(place: Place) -> dict:
    return {"name": place.bottleneck_name, "area_m2": place.bottleneck_m2, "polygon": place.bottleneck_polygon,
            "peak_share": place.peak_share, "bottleneck_share": place.bottleneck_share, "limit_per_m2": LIMIT,
            "limit_visitors": limit_visitors(place), "estimated": True}


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


def result_or_404(s: Session, judge_day: date | None, replay: bool) -> DailyResult:
    from fastapi import HTTPException
    row = find_result(s, judge_day, replay)
    if not row:
        if replay:
            raise HTTPException(404, f"{judge_day} 재현 결과 없음. POST /api/admin/replay 로 먼저 돌릴 것")
        raise HTTPException(404, "아직 판정 결과가 없음. POST /api/admin/run 으로 한 번 돌릴 것")
    return row


def row_for(s: Session, row: DailyResult, place: Place) -> dict | None:
    """한 장소의 대시보드 줄 (알림·문자 문안용)"""
    p = by_name(row.payload).get(place.name)
    return place_row(place, p, None, [], None) if p else None
