from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import account_out, check_password, current_account, make_token
from app.auth.models import Account
from app.core.db import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, s: Session = Depends(get_session)):
    acc = s.scalars(select(Account).where(Account.username == body.username)).first()
    if not acc or not check_password(body.password, acc.password_hash):
        raise HTTPException(401, "아이디 또는 비밀번호가 맞지 않음")
    return {"access_token": make_token(acc), "token_type": "bearer", "account": account_out(acc)}


@router.get("/me")
def me(acc: Account = Depends(current_account)):
    return account_out(acc)
