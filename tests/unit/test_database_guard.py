import pytest

from tests.conftest import assert_safe_test_database


def test_accepts_a_database_whose_name_ends_with_test():
    assert_safe_test_database("postgresql://u:p@localhost:5432/orbitdesk_test")


def test_rejects_the_development_database():
    with pytest.raises(RuntimeError):
        assert_safe_test_database("postgresql://u:p@localhost:5433/orbitdesk")


def test_rejects_a_name_that_only_contains_test():
    with pytest.raises(RuntimeError):
        assert_safe_test_database("postgresql://u:p@localhost:5432/orbitdesk_testing")


def test_rejects_a_url_without_a_database_name():
    with pytest.raises(RuntimeError):
        assert_safe_test_database("postgresql://u:p@localhost:5432")
