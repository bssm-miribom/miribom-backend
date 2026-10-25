"""miribom_ai가 읽는 작업 폴더(MIRIBOM_HOME) 준비.
places.csv는 DB 장소 + 별칭으로 판정 때마다 새로 쓰고, models/·data/는 miribom-ai 레포 것을 그대로 연결함"""
import csv
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db import Alias, Place

HOME = Path(settings.miribom_home)
FIELDS = ["place", "keywords", "lat", "lon", "base_rest", "base_work", "bottleneck_m2", "peak_share",
          "bottleneck_share", "force_watch", "note"]


def prepare():
    os.environ["MIRIBOM_HOME"] = str(HOME)   # miribom_ai를 불러오기 전에 정해야 함
    HOME.mkdir(parents=True, exist_ok=True)
    for name in ("models", "data"):
        link, target = HOME / name, Path(settings.miribom_ai_dir) / name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(target, target_is_directory=True)


def write_places(s, alias_before: datetime | None = None):
    """alias_before를 주면 그 시각 전에 등록된 별칭만 씀 (과거 재현 때 미래 정보 차단)"""
    q = select(Alias)
    if alias_before is not None:
        q = q.where(Alias.created_at < alias_before)
    aliases: dict[str, list[str]] = {}
    for a in s.scalars(q):
        aliases.setdefault(a.place_id, []).append(a.alias)
    with open(HOME / "places.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for p in s.scalars(select(Place).order_by(Place.id)):
            kw = "|".join([*p.keywords.split("|"), *aliases.get(p.id, [])])
            w.writerow([p.name, kw, p.lat, p.lon, p.base_rest, p.base_work, p.bottleneck_m2, p.peak_share,
                        p.bottleneck_share, p.force_watch, p.note])
