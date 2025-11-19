from pydantic import BaseModel

class TokenModel(BaseModel):
    token: str

class CookieModel(BaseModel):
    cookie: str

class CredsModel(BaseModel):
    username: str
    password: str

class SubmitModel(BaseModel):
    challenge_id: int | None = None
    flag: str
    challenge_name: str | None = None
