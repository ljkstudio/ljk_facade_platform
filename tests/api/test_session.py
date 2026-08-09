"""API session endpoint tests."""

from fastapi.testclient import TestClient

from api.server import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_session_flow():
    r = client.get("/api/session")
    assert r.status_code == 200
    assert r.json()["status"] == "idle"

    r = client.put(
        "/api/session/params",
        json={
            "params": {
                "width": 1200,
                "length": 1000,
                "spacing": 200,
                "max_height": 400,
                "min_height": 0,
                "rod_base_length": 300,
                "panel_name": "P-001",
            }
        },
    )
    assert r.status_code == 200
    assert r.json()["params"]["width"] == 1200

    r = client.post("/api/session/compute-request")
    assert r.status_code == 200
    assert r.json()["status"] == "compute_requested"

    r = client.post(
        "/api/session/sync",
        json={
            "result": {
                "nx": 6,
                "ny": 6,
                "grid_pts": [{"x": 0, "y": 0, "z": 0}],
                "pin_heights": [200.0],
                "pin_tops": [{"x": 0, "y": 0, "z": 200}],
                "clamp_flags": [False],
                "extension_flags": [False],
                "info": "test",
            }
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "synced"
    assert r.json()["gh_connected"] is True


def test_gh_ping():
    r = client.post("/api/session/gh-ping", json={"client_id": "test"})
    assert r.status_code == 200
    assert r.json()["gh_connected"] is True
