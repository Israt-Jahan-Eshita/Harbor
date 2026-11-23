"""Integration smoke test for /healthz and request ID middleware."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}
    assert "X-Request-Id" in response.headers
    assert len(response.headers["X-Request-Id"]) > 0

    head_resp = client.head("/healthz")
    assert head_resp.status_code == 200
    assert "X-Request-Id" in head_resp.headers
