import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_api_generate_and_status():
    res = client.post(
        "/api/generate-course",
        json={
            "material_type": "transcript",
            "content": "Python variables store data values. Functions perform tasks.",
            "title": "Python Basics Course",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "job_id" in data

    job_id = data["job_id"]
    status_res = client.get(f"/api/generate-course/{job_id}/status")
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["job_id"] == job_id
    assert "stages" in st_data
