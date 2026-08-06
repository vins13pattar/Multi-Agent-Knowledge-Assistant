import os
import time
from typing import Dict
import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Refusing to start with an insecure default — "
        "set JWT_SECRET to a long random value (see .env.example)."
    )
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def sign_jwt(user_id: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "expires": time.time() + (ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt(token: str) -> dict:
    try:
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    return decoded_token if decoded_token["expires"] >= time.time() else None
