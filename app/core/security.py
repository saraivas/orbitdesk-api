from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.core.config import (
  SECRET_KEY,
  ALGORITHM,
  ACCESS_TOKEN_EXPIRE_MINUTES,
  REFRESH_TOKEN_EXPIRE_DAYS,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
  return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
  return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, sid: str) -> str:
  expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
  payload = {"sub": user_id, "sid": sid, "exp": expire, "type": "access"}
  return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, sid: str, jti: str, session_expires_at: int) -> str:
  """Refresh token valid for 7 days, but never past the end of its session."""
  now = datetime.now(timezone.utc)
  session_end = datetime.fromtimestamp(session_expires_at, timezone.utc)
  expire = min(now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), session_end)
  payload = {
    "sub": user_id,
    "sid": sid,
    "jti": jti,
    "iat": now,
    "exp": expire,
    "type": "refresh",
  }
  return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
  try:
      payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
      return payload
  except JWTError:
      return None
