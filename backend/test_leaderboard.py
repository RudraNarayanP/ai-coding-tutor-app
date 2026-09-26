import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.user_store import UserStore, UserProfile

client = TestClient(app)


def test_user_store_starts_empty_without_fake_seeds(tmp_path: Path):
    store_file = tmp_path / "test_users.json"
    store1 = UserStore(storage_path=store_file)

    # No demo / fake names — empty board until a real learner joins
    assert store1.get_leaderboard("anyone") == []

    store1.get_or_create_user("user_alice", "Alice")
    store1.set_user_xp("user_alice", 250)

    store1.get_or_create_user("user_bob", "Bob")
    store1.set_user_xp("user_bob", 150)

    store2 = UserStore(storage_path=store_file)
    lb2 = store2.get_leaderboard("user_alice")

    assert len(lb2) == 2
    top_user = lb2[0]
    assert top_user.username == "Alice"
    assert top_user.xp == 250
    assert top_user.rank == 1
    assert top_user.is_current_user is True
    assert top_user.is_demo is False
    assert all(not e.is_demo for e in lb2)
    assert all("[Demo]" not in e.username for e in lb2)


def test_user_store_purges_legacy_demo_rows(tmp_path: Path):
    store_file = tmp_path / "legacy_users.json"
    store_file.write_text(
        json.dumps(
            [
                {
                    "user_id": "demo_alex",
                    "username": "[Demo] Alex",
                    "xp": 180,
                    "level": 2,
                    "streak": 1,
                    "is_demo": True,
                },
                {
                    "user_id": "real_1",
                    "username": "Rudra",
                    "xp": 40,
                    "level": 1,
                    "streak": 1,
                    "is_demo": False,
                },
            ]
        ),
        encoding="utf-8",
    )
    store = UserStore(storage_path=store_file)
    lb = store.get_leaderboard("real_1")
    assert len(lb) == 1
    assert lb[0].username == "Rudra"
    assert lb[0].is_demo is False
    persisted = json.loads(store_file.read_text(encoding="utf-8"))
    assert all(not row.get("is_demo") for row in persisted)
    assert all(not row["user_id"].startswith("demo_") for row in persisted)


def test_leaderboard_api_endpoint(tmp_path: Path, monkeypatch):
    import backend.main as main_module

    isolated_store = UserStore(storage_path=tmp_path / "test_users_state.json")
    monkeypatch.setattr(main_module, "user_store", isolated_store)

    res_prof = client.post(
        "/api/user/profile",
        json={"user_id": "test_user_api", "username": "TestAPIUser", "xp": 300},
    )
    assert res_prof.status_code == 200
    p_data = res_prof.json()
    assert p_data["xp"] == 300

    res_lb = client.get("/api/leaderboard?user_id=test_user_api")
    assert res_lb.status_code == 200
    lb_data = res_lb.json()
    assert isinstance(lb_data, list)
    assert len(lb_data) == 1

    rank1 = lb_data[0]
    assert rank1["username"] == "TestAPIUser"
    assert rank1["xp"] == 300
    assert rank1["rank"] == 1
    assert rank1["is_current_user"] is True
    assert rank1["is_demo"] is False


def test_exercise_xp_updates_leaderboard(tmp_path: Path, monkeypatch):
    """Awarding XP through the store re-ranks entries for live polling clients."""
    store_file = tmp_path / "live_users.json"
    store = UserStore(storage_path=store_file)
    store.get_or_create_user("a", "Ada")
    store.get_or_create_user("b", "Ben")
    store.set_user_xp("a", 10)
    store.set_user_xp("b", 20)
    assert store.get_leaderboard("a")[0].user_id == "b"

    store.update_user_xp("a", 15)  # Ada now 25
    lb = store.get_leaderboard("a")
    assert lb[0].user_id == "a"
    assert lb[0].xp == 25
    assert lb[0].rank == 1
