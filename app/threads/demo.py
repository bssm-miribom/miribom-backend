"""Threads 로그인 + 키워드 검색 화면 (Meta 앱 심사 녹화용, 나중에 대시보드 디자인으로 바꿈)

흐름: /threads/login → Threads 동의 화면 → /threads/callback → /threads/demo (장소별 검색 결과·가볼래 글 수)
- 토큰은 Redis에 1시간만 두고 이 화면에서 검색한 글은 저장하지 않음 (화면에 보여주기만 함)
- 가볼래 판정은 지금은 키워드 규칙. 방문 의도 모델 학습 후 miribom_ai.count_intent로 바꿈
"""
import html
import secrets
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import r
from app.core.config import settings
from app.core.db import get_session
from app.places.models import Alias, Place

router = APIRouter(prefix="/threads", tags=["threads-demo"], include_in_schema=False)

AUTH_URL = "https://threads.net/oauth/authorize"
TOKEN_URL = "https://graph.threads.net/oauth/access_token"
API = "https://graph.threads.net/v1.0"
SCOPES = "threads_basic,threads_keyword_search"
TTL = 3600
COOKIE = "miribom_threads"


def _redirect_uri() -> str:
    return f"{settings.public_base_url}/threads/callback"


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>미리봄 · Threads 연결</title>
<style>body{{font-family:-apple-system,sans-serif;max-width:760px;margin:40px auto;padding:0 16px;line-height:1.5}}
.btn{{display:inline-block;background:#000;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:8px;text-align:left}}
.post{{color:#444;font-size:14px;margin:4px 0}}.muted{{color:#888;font-size:13px}}</style></head><body>{body}</body></html>""")


@router.get("/login")
def login():
    if not settings.threads_app_id:
        raise HTTPException(503, "THREADS_APP_ID 미설정")
    state = secrets.token_urlsafe(16)
    r.setex(f"miribom:threads:state:{state}", 600, "1")
    q = urlencode({"client_id": settings.threads_app_id, "redirect_uri": _redirect_uri(),
                   "scope": SCOPES, "response_type": "code", "state": state})
    return RedirectResponse(f"{AUTH_URL}?{q}")


@router.get("/callback")
def callback(code: str = "", state: str = "", error_description: str = ""):
    if error_description:
        return _page(f"<h2>연결이 취소됨</h2><p>{html.escape(error_description)}</p><a href='/threads/start'>처음으로</a>")
    if not state or not r.delete(f"miribom:threads:state:{state}"):
        raise HTTPException(400, "state 불일치 (다시 로그인할 것)")
    res = requests.post(TOKEN_URL, data={"client_id": settings.threads_app_id,
                                         "client_secret": settings.threads_app_secret,
                                         "grant_type": "authorization_code",
                                         "redirect_uri": _redirect_uri(), "code": code}, timeout=30)
    if res.status_code != 200:
        raise HTTPException(502, f"토큰 교환 실패: {res.text[:200]}")
    sid = secrets.token_urlsafe(24)
    r.setex(f"miribom:threads:sid:{sid}", TTL, res.json()["access_token"])
    resp = RedirectResponse("/threads/demo")
    resp.set_cookie(COOKIE, sid, max_age=TTL, httponly=True, samesite="lax",
                    secure=settings.public_base_url.startswith("https"))
    return resp


@router.get("/start")
def start():
    return _page("""<h1>미리봄</h1>
<p>부산 관광지에 사람이 몰리기 전에 1~3일 앞서 혼잡을 예보하는 서비스입니다.</p>
<p>Threads에서 장소 이름이 들어간 공개 글을 검색해, 그 장소에 <b>가 보려는 글이 얼마나 늘었는지</b>를 혼잡 예보의 입력으로 씁니다.
작성자 정보는 저장하지 않고 장소별 하루 글 수만 남깁니다. 분류 모델 학습용 표본은 <a href="/privacy">개인정보처리방침</a>에 따라 보관 후 폐기합니다.</p>
<p><a class="btn" href="/threads/login">Threads로 연결하기</a></p>
<p class="muted"><a href="/privacy">개인정보처리방침</a></p>""")


def _keywords(s: Session) -> list[tuple[str, list[str]]]:
    out = []
    for p in s.scalars(select(Place).order_by(Place.name)):
        kws = [k for k in (p.keywords or "").split("|") if k][:1]
        kws += [a.alias for a in s.scalars(select(Alias).where(Alias.place_id == p.id))]
        out.append((p.name, kws or [p.name]))
    return out


def _search(token: str, q: str) -> list[dict]:
    res = requests.get(f"{API}/keyword_search", timeout=30, params={
        "q": q, "search_type": "RECENT", "fields": "id,text,timestamp", "limit": 25, "access_token": token})
    if res.status_code != 200:
        raise HTTPException(502, f"검색 실패 ({q}): {res.text[:200]}")
    return [d for d in res.json().get("data", []) if d.get("text")]


@router.get("/demo")
def demo(sid: str | None = Cookie(default=None, alias=COOKIE), s: Session = Depends(get_session)):
    token = r.get(f"miribom:threads:sid:{sid}") if sid else None
    if not token:
        return RedirectResponse("/threads/start")
    from miribom_ai.intent.baseline import predict   # 방문 의도 모델 학습 전 임시 규칙

    rows, details = [], []
    for name, kws in _keywords(s):
        posts = {d["id"]: d for kw in kws for d in _search(token, kw)}.values()
        texts = [d["text"] for d in posts]
        go = sum(predict(texts)) if texts else 0
        rows.append(f"<tr><td>{html.escape(name)}</td><td>{html.escape(', '.join(kws))}</td>"
                    f"<td>{len(texts)}</td><td><b>{go}</b></td></tr>")
        for d in list(posts)[:3]:
            details.append(f"<p class='post'>[{html.escape(name)}] {html.escape(d['text'][:120])} "
                           f"<span class='muted'>{html.escape(d.get('timestamp', '')[:10])}</span></p>")
    return _page(f"""<h1>장소별 Threads 검색 결과</h1>
<p class="muted">장소 검색어로 최근 공개 글을 검색해 '가볼래' 글 수를 셈. 이 숫자가 혼잡 예보 모델의 입력으로 들어감.</p>
<table><tr><th>장소</th><th>검색어</th><th>검색된 글</th><th>가볼래 글</th></tr>{''.join(rows)}</table>
<h3>검색된 글 예시 (저장하지 않음)</h3>{''.join(details) or "<p class='muted'>검색된 글 없음</p>"}
<p><a href="/threads/logout">연결 끊기</a> · <a href="/privacy">개인정보처리방침</a></p>""")


@router.get("/logout")
def logout(sid: str | None = Cookie(default=None, alias=COOKIE)):
    if sid:
        r.delete(f"miribom:threads:sid:{sid}")
    resp = RedirectResponse("/threads/start")
    resp.delete_cookie(COOKIE)
    return resp
