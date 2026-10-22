from functools import lru_cache

import redis

from app.core.config import REDIS_URL


@lru_cache(maxsize=1)
def _client() -> redis.Redis:
    # decode_responses: keys and values are text everywhere in this app.
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def get_redis() -> redis.Redis:
    """FastAPI dependency. Tests override it with a client on the test database."""
    return _client()
