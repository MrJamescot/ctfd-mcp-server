"""Pydantic models for request bodies and result payloads."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenModel(BaseModel):
    token: str = Field(min_length=1)


class CookieModel(BaseModel):
    cookie: str = Field(min_length=1)


class CredsModel(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class BaseUrlModel(BaseModel):
    url: str = Field(min_length=1)


class SubmitModel(BaseModel):
    challenge_id: int | None = None
    challenge_name: str | None = None
    flag: str
    confirm: bool = False