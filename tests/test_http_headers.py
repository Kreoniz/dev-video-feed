from fastapi import Response

from app.main import NO_STORE_HEADERS, apply_no_store_headers


def test_apply_no_store_headers_sets_expected_json_cache_headers() -> None:
    response = Response()

    apply_no_store_headers(response)

    for name, value in NO_STORE_HEADERS.items():
        assert response.headers[name] == value
