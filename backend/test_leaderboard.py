import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.user_store import UserStore, UserProfile

client = TestClient(app)


def test_user_store_persistence(tmp_path: Path):
    store_file = tmp_path / "test_users.json"
    store1 = UserStore(storage_path=store_file)

    # Verify default users seeded
    lb1 = store1.get_leaderboard("default_user")
    assert len(lb1) >= 5

    # Create new users with different XP
    store1.get_or_create_user("user_alice", "Alice")
    store1.set_user_xp("user_alice", 250)

    store1.get_or_create_user("user_bob", "Bob")
    store1.set_user_xp("user_bob", 150)

    # Reload store from disk
    store2 = UserStore(storage_path=store_file)
    lb2 = store2.get_leaderboard("user_alice")

    # Verify Alice is top ranked with 250 XP
    top_user = lb2[0]
    assert top_user.username == "Alice"
    assert top_user.xp == 250
    assert top_user.rank == 1
    assert top_user.is_current_user is True


def test_leaderboard_api_endpoint():
    # Update profile
    res_prof = client.post(
        "/api/user/profile",
        json={"user_id": "test_user_api", "username": "TestAPIUser", "xp": 300},
    )
    assert res_prof.status_code == 200
    p_data = res_prof.json()
    assert p_data["xp"] == 300

    # Fetch leaderboard
    res_lb = client.get("/api/leaderboard?user_id=test_user_api")
    assert res_lb.status_code == 200
    lb_data = res_lb.json()
    assert isinstance(lb_data, list)
    assert len(lb_data) > 0

    # TestAPIUser should be rank 1
    rank1 = lb_data[0]
    assert rank1["username"] == "TestAPIUser"
    assert rank1["xp"] == 300
    assert rank1["rank"] == 1
    assert rank1["is_current_user"] is True
