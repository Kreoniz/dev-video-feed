from app.main import (
    NO_STORE_CACHE_HEADERS,
    NO_STORE_JSON_CONTENT_TYPE,
    NoStoreJSONResponse,
)


def test_no_store_json_response_sets_expected_headers() -> None:
    response = NoStoreJSONResponse({"ok": True})

    for name, value in NO_STORE_CACHE_HEADERS.items():
        assert response.headers[name] == value
    assert response.headers["content-type"] == NO_STORE_JSON_CONTENT_TYPE
