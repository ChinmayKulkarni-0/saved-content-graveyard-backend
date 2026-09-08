import time
from datetime import timedelta

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import create_access_token, get_current_user


async def test_token_roundtrip():
    token = create_access_token(data={"sub": "user-1"})
    payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "user-1"
    assert payload["exp"] > time.time()


async def test_get_current_user_returns_sub():
    token = create_access_token(data={"sub": "user-2"})
    assert await get_current_user(token) == "user-2"


async def test_tampered_token_is_rejected():
    token = create_access_token(data={"sub": "user-3"})
    tampered = token[:-2] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(tampered)
    assert exc_info.value.status_code == 401


async def test_token_signed_with_other_key_is_rejected():
    token = pyjwt.encode({"sub": "user-4"}, "attacker-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token)
    assert exc_info.value.status_code == 401


async def test_expired_token_is_rejected():
    token = create_access_token(
        data={"sub": "user-5"}, expires_delta=timedelta(seconds=-10)
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token)
    assert exc_info.value.status_code == 401


async def test_token_without_sub_is_rejected():
    token = create_access_token(data={"scope": "nothing"})
    with pytest.raises(HTTPException):
        await get_current_user(token)