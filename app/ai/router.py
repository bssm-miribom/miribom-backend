"""AI 연동: 모델 상태 카드, 방문 의도 분류 시연. 판정 자체는 judge/jobs.py가 miribom_ai.run_daily()로 돌림"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.auth.models import Account
from app.auth.service import city_account
from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["AI"])


@router.get("/models")
def models(acc: Account = Depends(city_account)):
    """규모 예측·의도 분류·급증 탐지 모델 상태와 성능 (models/·results/ 파일을 읽음)"""
    import miribom_ai
    out = miribom_ai.model_status(demo=settings.miribom_demo)
    out["threads"] = {"collect": settings.intent_collect,
                      "token": bool(settings.threads_access_token),
                      "note": "keyword_search 앱 심사 전에는 내 글만 검색됨"}
    return out


class ClassifyIn(BaseModel):
    texts: list[str] = Field(min_length=1)


@router.post("/intent/classify")
async def classify(body: ClassifyIn, acc: Account = Depends(city_account)):
    """문장 → 가볼래 / 그냥 언급 (KcELECTRA). 입력 문장은 저장하지 않음"""
    if len(body.texts) > settings.intent_max_texts:
        raise HTTPException(400, f"한 번에 {settings.intent_max_texts}문장까지")
    if any(len(t) > 1000 for t in body.texts):
        raise HTTPException(400, "문장 하나는 1000자까지")
    import miribom_ai
    st = miribom_ai.model_status()["intent"]
    if not st["ready"]:
        raise HTTPException(503, f"방문 의도 모델을 쓸 수 없음: {st['reason']}")
    try:
        results = await run_in_threadpool(miribom_ai.label_texts, body.texts)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")
    return {"results": results, "model": st["name"], "threshold": st["threshold"]}
