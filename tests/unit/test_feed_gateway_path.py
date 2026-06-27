from nautilus_mt5.feed.gateway import feed_path_matches, normalize_feed_request_path


def test_normalize_standard_path() -> None:
    assert normalize_feed_request_path("/mt5-feed", "/mt5-feed") == "/mt5-feed"
    assert feed_path_matches("/mt5-feed", "/mt5-feed")


def test_normalize_mql5_full_url_path() -> None:
    raw = "ws://127.0.0.1:8765/mt5-feed"
    assert normalize_feed_request_path(raw, "/mt5-feed") == "/mt5-feed"
    assert feed_path_matches(raw, "/mt5-feed")


def test_normalize_mql5_url_with_query() -> None:
    assert feed_path_matches("ws://127.0.0.1:8765/mt5-feed?x=1", "/mt5-feed")


def test_reject_wrong_path() -> None:
    assert not feed_path_matches("ws://127.0.0.1:8765/other", "/mt5-feed")
    assert not feed_path_matches("/wrong", "/mt5-feed")
