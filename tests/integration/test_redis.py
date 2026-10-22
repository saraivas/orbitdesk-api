def test_redis_test_database_is_reachable(redis_client):
    assert redis_client.ping() is True


def test_fixture_leaves_a_clean_database_after_a_test_writes_to_it(redis_client):
    # Pairs with the next test: this one writes, the next one must not see it.
    redis_client.set("orbitdesk:v1:probe", "written")
    assert redis_client.get("orbitdesk:v1:probe") == "written"


def test_fixture_flushes_between_tests(redis_client):
    assert redis_client.get("orbitdesk:v1:probe") is None
