"""처음 실행 때 장소(miribom-ai/places.csv)와 시연용 계정을 DB에 넣음"""
import csv
import logging
from pathlib import Path

from sqlalchemy import select

from app.auth.service import hash_password
from app.core.config import settings
from app.auth.models import Account
from app.core.db import SessionLocal
from app.places.models import Place

log = logging.getLogger("miribom.seed")

# places.csv에 없는 값 (영문 ID, 구·군, 병목 구간 이름) [팀 확인]
PLACE_META = {
    "북항친수공원": ("bukhang", "동구", "해상육교 진입로"),
    "광안리해수욕장": ("gwangalli", "수영구", None),
    "해운대해수욕장": ("haeundae", "해운대구", None),
    "감천문화마을": ("gamcheon", "사하구", None),
    "흰여울문화마을": ("huinyeoul", "영도구", None),
}

# 장소 좌표 공식 출처: 한국관광공사 TourAPI 국문 관광정보(KorService2 searchKeyword2) mapy·mapx, 2026-11-26 조회
# 이름: (contentid, 위도, 경도, places.csv 옛 좌표). places.csv 좌표는 출처 기록이 없어서 이 값으로 바꿈
TOUR_COORDS = {
    "북항친수공원": ("3426656", 35.1144199, 129.0466221, (35.1150, 129.0450)),     # '부산북항 친수공원'
    "광안리해수욕장": ("126078", 35.1531933, 129.1189761, (35.1532, 129.1186)),
    "해운대해수욕장": ("126081", 35.1590840, 129.1602786, (35.1587, 129.1604)),
    "감천문화마을": ("1997221", 35.0974607, 129.0105970, (35.0975, 129.0106)),     # '부산 감천문화마을'
    "흰여울문화마을": ("2684712", 35.0798897, 129.0435396, (35.0782, 129.0447)),
}

SEED_ACCOUNTS = [
    ("busan", "부산시 재난안전과", "city", None),
    ("donggu", "동구청 안전도시과", "district", "동구"),
    ("police_dong", "부산동부경찰서", "police", None),   # 조치 요청 받은 장소만 봄 (A-11)
]


def _num(v):
    return float(v) if v not in (None, "") else None


def seed_places(s):
    if s.scalars(select(Place).limit(1)).first():
        return
    path = Path(settings.miribom_ai_dir) / "places.csv"
    with open(path, encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            pid, district, bname = PLACE_META.get(row["place"], (f"place{i + 1}", None, None))
            tc = TOUR_COORDS.get(row["place"])
            lat, lon = (tc[1], tc[2]) if tc else (_num(row["lat"]), _num(row["lon"]))
            s.add(Place(id=pid, name=row["place"], district=district, lat=lat, lon=lon,
                        keywords=row["keywords"], base_rest=_num(row["base_rest"]), base_work=_num(row["base_work"]),
                        bottleneck_name=bname, bottleneck_m2=_num(row["bottleneck_m2"]),
                        peak_share=_num(row["peak_share"]), bottleneck_share=_num(row["bottleneck_share"]),
                        force_watch=int(row.get("force_watch") or 0), note=row.get("note")))
    log.info("장소 넣음: %s", path)


def fix_coords(s):
    """이미 만든 DB: 좌표가 places.csv 옛 값 그대로인 장소만 TourAPI 좌표로 바꿈 (관리자가 고친 값은 안 건드림)"""
    for p in s.scalars(select(Place)):
        tc = TOUR_COORDS.get(p.name)
        if tc and p.lat is not None and p.lon is not None and (round(p.lat, 4), round(p.lon, 4)) == tc[3]:
            p.lat, p.lon = tc[1], tc[2]
            log.info("좌표 TourAPI로 바꿈: %s", p.name)


def seed_accounts(s):
    """없는 시연용 계정만 넣음 (이미 있는 계정의 비밀번호는 안 바꿈)"""
    have = set(s.scalars(select(Account.username)))
    new = [a for a in SEED_ACCOUNTS if a[0] not in have]
    for username, org_name, org_type, district in new:
        s.add(Account(username=username, password_hash=hash_password(settings.seed_password),
                      org_name=org_name, org_type=org_type, district=district))
    if new:
        log.info("시연용 계정 넣음: %s", ", ".join(a[0] for a in new))


def seed():
    with SessionLocal() as s:
        seed_places(s)
        fix_coords(s)
        seed_accounts(s)
        s.commit()
