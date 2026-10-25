"""처음 실행 때 장소(miribom-ai/places.csv)와 시연용 계정을 DB에 넣음"""
import csv
import logging
from pathlib import Path

from sqlalchemy import select

from app.auth import hash_password
from app.config import settings
from app.db import Account, Place, SessionLocal

log = logging.getLogger("miribom.seed")

# places.csv에 없는 값 (영문 ID, 구·군, 병목 구간 이름) [팀 확인]
PLACE_META = {
    "북항친수공원": ("bukhang", "동구", "해상육교 진입로"),
    "광안리해수욕장": ("gwangalli", "수영구", None),
    "해운대해수욕장": ("haeundae", "해운대구", None),
    "감천문화마을": ("gamcheon", "사하구", None),
    "흰여울문화마을": ("huinyeoul", "영도구", None),
}

SEED_ACCOUNTS = [
    ("busan", "부산시 재난안전과", "city", None),
    ("donggu", "동구청 안전도시과", "district", "동구"),
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
            s.add(Place(id=pid, name=row["place"], district=district, lat=_num(row["lat"]), lon=_num(row["lon"]),
                        keywords=row["keywords"], base_rest=_num(row["base_rest"]), base_work=_num(row["base_work"]),
                        bottleneck_name=bname, bottleneck_m2=_num(row["bottleneck_m2"]),
                        peak_share=_num(row["peak_share"]), bottleneck_share=_num(row["bottleneck_share"]),
                        force_watch=int(row.get("force_watch") or 0), note=row.get("note")))
    log.info("장소 넣음: %s", path)


def seed_accounts(s):
    if s.scalars(select(Account).limit(1)).first():
        return
    for username, org_name, org_type, district in SEED_ACCOUNTS:
        s.add(Account(username=username, password_hash=hash_password(settings.seed_password),
                      org_name=org_name, org_type=org_type, district=district))
    log.info("시연용 계정 넣음: %s", ", ".join(a[0] for a in SEED_ACCOUNTS))


def seed():
    with SessionLocal() as s:
        seed_places(s)
        seed_accounts(s)
        s.commit()
