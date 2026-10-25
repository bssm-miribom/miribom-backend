"""로그인과 기관별 권한 (A-15). 비밀번호는 PBKDF2, 토큰은 JWT"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Account, Place, get_session

bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    return salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()


def check_password(pw: str, stored: str) -> bool:
    salt, h = stored.split("$", 1)
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex(), h)


def make_token(acc: Account) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_hours)
    return jwt.encode({"sub": acc.username, "exp": exp}, settings.jwt_secret, algorithm="HS256")


def account_out(acc: Account) -> dict:
    return {"username": acc.username, "org_name": acc.org_name, "org_type": acc.org_type,
            "district": acc.district, "can_edit": acc.org_type == "city"}


def current_account(cred: HTTPAuthorizationCredentials | None = Depends(bearer),
                    s: Session = Depends(get_session)) -> Account:
    if not cred:
        raise HTTPException(401, "로그인 필요")
    try:
        sub = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "로그인이 만료됐거나 토큰이 틀림")
    acc = s.scalars(select(Account).where(Account.username == sub)).first()
    if not acc:
        raise HTTPException(401, "없는 계정")
    return acc


def city_account(acc: Account = Depends(current_account)) -> Account:
    if acc.org_type != "city":
        raise HTTPException(403, "부산시 계정만 할 수 있음")
    return acc


def city_or_token(cred: HTTPAuthorizationCredentials | None = Depends(bearer), x_admin_token: str = Header(default=""),
                  s: Session = Depends(get_session)) -> str:
    """수동 실행용: 부산시 계정 또는 ADMIN_TOKEN"""
    if settings.admin_token and hmac.compare_digest(x_admin_token, settings.admin_token):
        return "admin-token"
    return city_account(current_account(cred, s)).username


def can_see(acc: Account, place: Place) -> bool:
    if acc.org_type == "city":
        return True
    if acc.org_type == "district":
        return place.district == acc.district
    return place.id in (acc.place_ids or [])
