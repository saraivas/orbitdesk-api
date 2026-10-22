import os

import pytest
import redis
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.db.base import Base
from app.core.redis import get_redis
from app.db.session import get_db

DEFAULT_TEST_DATABASE_URL = "postgresql://orbitdesk:orbitdesk@localhost:5433/orbitdesk_test"


def assert_safe_test_database(url: str) -> None:
    """Refuse to run unless the database name ends with `_test`.

    The fixtures below create and drop every table on each test, so pointing
    them at a development or production database would destroy its data.
    """
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests: database {name!r} does not end with '_test'. "
            "Set TEST_DATABASE_URL to a dedicated test database."
        )


# Tests use their own variable on purpose. DATABASE_URL is the application's
# database (development, or production when running migrations), and the
# fixtures drop all tables on teardown.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
assert_safe_test_database(TEST_DATABASE_URL)

DEFAULT_TEST_REDIS_URL = "redis://localhost:6380/15"


def assert_safe_test_redis(url: str) -> None:
    """Refuse to run against Redis database 0, the one the application uses.

    The `redis_client` fixture flushes its whole database before and after
    each test.
    """
    db = int(make_url(url.replace("redis://", "postgresql://", 1)).database or 0)
    if db == 0:
        raise RuntimeError(
            "Refusing to run tests: TEST_REDIS_URL uses Redis database 0, which "
            "the application uses. Use another database number, for example /15."
        )


TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", DEFAULT_TEST_REDIS_URL)
assert_safe_test_redis(TEST_REDIS_URL)

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def redis_client():
    r = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    r.flushdb()
    yield r
    r.flushdb()
    r.close()


@pytest.fixture(scope="function")
def client(db_session, redis_client):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = lambda: redis_client
    yield TestClient(app)
    app.dependency_overrides.clear()
