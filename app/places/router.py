"""장소 정보 입력 (A-06 별칭, A-08 병목 구간, 장소 수정·추가)"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Account
from app.auth.service import can_see, city_account, current_account
from app.core.config import KST, settings
from app.core.db import get_session
from app.dashboard.views import bottleneck_out
from app.places.geo import polygon_area_m2
from app.places.models import Alias, Place

router = APIRouter(prefix="/admin", tags=["장소 입력"])


def applies_from(t: datetime) -> str:
    """판정 작업이 장소·별칭을 매번 새로 읽으므로, 이 시각 뒤 처음 돌아오는 매일 판정(기본 06시)부터 반영됨"""
    t = t.astimezone(KST)
    run_at = t.replace(hour=settings.daily_hour, minute=settings.daily_minute, second=0, microsecond=0)
    return str((t if t < run_at else t + timedelta(days=1)).date())


def place_out(s: Session, p: Place) -> dict:
    return {"id": p.id, "name": p.name, "district": p.district, "lat": p.lat, "lon": p.lon,
            "keywords": [k for k in (p.keywords or "").split("|") if k],
            "aliases": [a.alias for a in s.scalars(select(Alias).where(Alias.place_id == p.id))],
            "base_rest": p.base_rest, "base_work": p.base_work, "force_watch": bool(p.force_watch), "note": p.note,
            "bottleneck": bottleneck_out(p)}


@router.get("/places")
def places(acc: Account = Depends(current_account), s: Session = Depends(get_session)):
    """별칭·병목 입력 때 고를 장소 목록 (관할 안만)"""
    al: dict[str, list[str]] = {}
    for a in s.scalars(select(Alias)):
        al.setdefault(a.place_id, []).append(a.alias)
    return [{"id": p.id, "name": p.name, "district": p.district, "aliases": al.get(p.id, [])}
            for p in s.scalars(select(Place).order_by(Place.name)) if can_see(acc, p)]


def _name_taken(s: Session, name: str, except_id: str | None = None) -> bool:
    p = s.scalars(select(Place).where(Place.name == name)).first()
    return bool(s.scalars(select(Alias).where(Alias.alias == name)).first() or (p and p.id != except_id))


# ===== 장소 추가·수정 =====
class PlaceIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    name: str = Field(min_length=1, max_length=60)
    district: str | None = None
    lat: float | None = None
    lon: float | None = None
    keywords: list[str] = Field(default_factory=list, max_length=20)
    base_rest: float | None = Field(default=None, gt=0)
    base_work: float | None = Field(default=None, gt=0)


class PlacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    district: str | None = None
    lat: float | None = None
    lon: float | None = None
    keywords: list[str] | None = Field(default=None, min_length=1, max_length=20)
    base_rest: float | None = Field(default=None, gt=0)
    base_work: float | None = Field(default=None, gt=0)
    force_watch: bool | None = None
    note: str | None = None


def _kw(words: list[str]) -> str:
    return "|".join(dict.fromkeys(w.strip() for w in words if w.strip() and "|" not in w))


@router.post("/places", status_code=201)
def add_place(body: PlaceIn, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    name = body.name.strip()
    if s.get(Place, body.id) or _name_taken(s, name):
        raise HTTPException(409, "이미 있는 장소 id 또는 이름")
    p = Place(id=body.id, name=name, district=body.district, lat=body.lat, lon=body.lon,
              keywords=_kw(body.keywords) or name, base_rest=body.base_rest, base_work=body.base_work, force_watch=0)
    s.add(p)
    s.commit()
    return {**place_out(s, p), "applies_from": applies_from(datetime.now(KST))}


@router.patch("/places/{place_id}")
def patch_place(place_id: str, body: PlacePatch, acc: Account = Depends(city_account),
                s: Session = Depends(get_session)):
    p = s.get(Place, place_id)
    if not p:
        raise HTTPException(404, "없는 장소")
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        data["name"] = data["name"].strip()
        if _name_taken(s, data["name"], except_id=p.id):
            raise HTTPException(409, "이미 쓰는 이름")
    if "keywords" in data:
        data["keywords"] = _kw(data["keywords"]) or p.name
    if "force_watch" in data:
        data["force_watch"] = int(data["force_watch"])
    for k, v in data.items():
        setattr(p, k, v)
    s.commit()
    return {**place_out(s, p), "applies_from": applies_from(datetime.now(KST))}


# ===== 병목 구간 (A-08) =====
class BottleneckIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    polygon: list[list[float]] | None = Field(default=None, description="[[경도, 위도], ...] 3개 이상")
    area_m2: float | None = Field(default=None, gt=0, description="다각형이 없을 때 직접 입력")
    peak_share: float | None = Field(default=None, gt=0, le=1, description="하루 방문객 중 피크 1시간 비중")
    bottleneck_share: float | None = Field(default=None, gt=0, le=1, description="피크 때 병목을 지나는 비율")

    @field_validator("polygon")
    @classmethod
    def _poly(cls, v):
        if v is not None and (len(v) < 3 or any(len(p) != 2 for p in v)):
            raise ValueError("polygon은 [경도, 위도] 3개 이상")
        return v


@router.put("/places/{place_id}/bottleneck")
def set_bottleneck(place_id: str, body: BottleneckIn, acc: Account = Depends(city_account),
                   s: Session = Depends(get_session)):
    p = s.get(Place, place_id)
    if not p:
        raise HTTPException(404, "없는 장소")
    if body.polygon is None and body.area_m2 is None:
        raise HTTPException(400, "polygon 또는 area_m2 중 하나는 있어야 함")
    p.bottleneck_name = body.name
    p.bottleneck_polygon = body.polygon
    p.bottleneck_m2 = round(polygon_area_m2(body.polygon), 1) if body.polygon else body.area_m2
    if body.peak_share is not None:
        p.peak_share = body.peak_share
    if body.bottleneck_share is not None:
        p.bottleneck_share = body.bottleneck_share
    s.commit()
    return {"id": p.id, "bottleneck": bottleneck_out(p), "applies_from": applies_from(datetime.now(KST))}


# ===== 별칭 (A-06) =====
class AliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=60)
    place_id: str


def _alias_out(a: Alias) -> dict:
    return {"id": a.id, "alias": a.alias, "place_id": a.place_id, "created_at": a.created_at.isoformat(),
            "applies_from": applies_from(a.created_at)}


@router.get("/aliases")
def list_aliases(acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    return [_alias_out(a) for a in s.scalars(select(Alias).order_by(Alias.created_at.desc()))]


@router.post("/aliases", status_code=201)
def add_alias(body: AliasIn, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    name = body.alias.strip()
    if not s.get(Place, body.place_id):
        raise HTTPException(404, "없는 장소")
    if _name_taken(s, name):
        raise HTTPException(409, "이미 등록된 별칭")
    a = Alias(alias=name, place_id=body.place_id, created_by=acc.username)
    s.add(a)
    s.commit()
    s.refresh(a)
    return _alias_out(a)


@router.delete("/aliases/{alias_id}", status_code=204)
def delete_alias(alias_id: int, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    a = s.get(Alias, alias_id)
    if not a:
        raise HTTPException(404, "없는 별칭")
    s.delete(a)
    s.commit()
