from mcp_server.core.config import Settings


def test_default_is_false():
    s = Settings()
    assert s.ENABLE_PI_POINT_RESOLVER_V2 is False


def test_can_be_enabled():
    s = Settings(ENABLE_PI_POINT_RESOLVER_V2=True)
    assert s.ENABLE_PI_POINT_RESOLVER_V2 is True


def test_can_be_disabled():
    s = Settings(ENABLE_PI_POINT_RESOLVER_V2=False)
    assert s.ENABLE_PI_POINT_RESOLVER_V2 is False
