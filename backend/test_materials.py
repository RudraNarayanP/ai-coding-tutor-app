import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_get_materials_list():
    res = client.get("/api/materials")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 15

    # Filter by language
    py_res = client.get("/api/materials?language=python")
    assert py_res.status_code == 200
    py_data = py_res.json()
    assert len(py_data) >= 3
    assert all(m["language"] == "python" for m in py_data)


def test_complete_material_idempotency():
    # Submit correct answer for Kaggle Python material
    ans = "[x for x in numbers if x % 2 == 0]"
    mat_id = "kaggle-learn-python"

    # Ensure clean starting state for this material
    res1 = client.post(f"/api/materials/{mat_id}/complete", json={"user_answer": ans})
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["passed"] is True

    # Submit second time (duplicate request)
    res2 = client.post(f"/api/materials/{mat_id}/complete", json={"user_answer": ans})
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["passed"] is True
    assert d2["xp_awarded"] == 0  # Idempotent: 0 XP on duplicate completion


def test_complete_material_wrong_answer():
    res = client.post("/api/materials/automate-boring-stuff/complete", json={"user_answer": "wrong answer"})
    assert res.status_code == 200
    d = res.json()
    assert d["passed"] is False
    assert d["xp_awarded"] == 0
