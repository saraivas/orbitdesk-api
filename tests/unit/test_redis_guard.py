import pytest

from tests.conftest import assert_safe_test_redis


def test_accepts_a_non_default_redis_database():
    assert_safe_test_redis("redis://localhost:6380/15")


def test_rejects_database_zero_explicitly():
    with pytest.raises(RuntimeError):
        assert_safe_test_redis("redis://localhost:6380/0")


def test_rejects_a_url_without_a_database_number():
    with pytest.raises(RuntimeError):
        assert_safe_test_redis("redis://localhost:6380")
