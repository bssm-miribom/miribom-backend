"""Threads 앱 콜백: 연결 해제(deauthorize), 데이터 삭제(delete).
Meta가 signed_request(폼 값)를 POST로 보냄. 앱 시크릿으로 서명 확인 후 처리.
미리봄은 글 원문·작성자 정보를 저장하지 않아서 지울 개인 데이터가 없음 → 요청 기록만 남기고 확인 코드를 돌려줌"""
import base64
import hashlib
import hmac
import json
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import DeletionRequest, get_session

router = APIRouter(prefix="/threads", tags=["threads"])


def _b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def parse_signed_request(signed_request: str) -> dict:
    if not settings.threads_app_secret:
        raise HTTPException(503, "THREADS_APP_SECRET 미설정")
    try:
        sig, body = signed_request.split(".", 1)
        data = json.loads(_b64(body))
    except Exception:
        raise HTTPException(400, "signed_request 형식 오류")
    expected = hmac.new(settings.threads_app_secret.encode(), body.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64(sig), expected):
        raise HTTPException(400, "서명 불일치")
    return data


def _record(s: Session, kind: str) -> str:
    code = secrets.token_hex(8)
    s.add(DeletionRequest(code=code, kind=kind))
    s.commit()
    return code


@router.post("/deauthorize")
def deauthorize(signed_request: str = Form(...), s: Session = Depends(get_session)):
    parse_signed_request(signed_request)
    _record(s, "deauthorize")
    return {"ok": True}


@router.post("/delete")
def delete(signed_request: str = Form(...), s: Session = Depends(get_session)):
    parse_signed_request(signed_request)
    code = _record(s, "delete")
    return {"url": f"{settings.public_base_url}/api/threads/delete/{code}", "confirmation_code": code}


@router.get("/delete/{code}")
def delete_status(code: str, s: Session = Depends(get_session)):
    row = s.scalars(select(DeletionRequest).where(DeletionRequest.code == code)).first()
    if not row:
        raise HTTPException(404, "요청 없음")
    return {"confirmation_code": code, "status": row.status, "requested_at": row.created_at.isoformat(),
            "note": "미리봄은 게시글 원문·작성자 정보를 저장하지 않아 삭제할 개인 데이터가 없음"}
