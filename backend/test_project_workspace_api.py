"""End-to-end API tests for the Create Course guided-project workspace.

Exercises the full flow against the real FastAPI app + Docker sandbox:
create → save workspace → run → NEXT (verify) → complete. Also verifies the
feature is isolated (does not disturb existing courses/lessons).
"""
from fastapi.testclient import TestClient

import backend.main as main_module

client = TestClient(main_module.app)


WORD_COUNT_TRANSCRIPT = """
In this tutorial we build a word frequency counter in Python.
First, import the collections module.
Next, define a function called count_words that takes a text string.
Then create a variable called sample containing some text.
Call count_words on the sample.
Finally, print the result so you can see the counts.
"""

SOLUTION = (
    "import collections\n"
    "from collections import Counter\n\n"
    "def count_words(text):\n"
    "    return Counter(text.split())\n\n"
    "sample = 'a b a c a b'\n"
    "print(count_words(sample))\n"
)


def _create_project():
    res = client.post(
        "/api/create-course/projects",
        json={"material_type": "transcript", "content": WORD_COUNT_TRANSCRIPT, "title": "Word Frequency Counter"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_create_project_is_source_grounded():
    data = _create_project()
    assert data["course_id"].startswith("project-")
    titles = [m["title"] for m in data["milestones"]]
    assert any("collections" in t for t in titles)
    assert any("count_words" in t for t in titles)
    assert data["completion_percent"] == 0
    assert data["tech_stack"] == ["collections"] or "collections" in data["tech_stack"]


def test_ungroundable_source_returns_clear_error():
    res = client.post(
        "/api/create-course/projects",
        json={"material_type": "transcript", "content": "I like turtles and nice weather.", "title": "Vlog"},
    )
    assert res.status_code == 422
    assert "message" in res.json()["detail"]


def test_full_build_flow_completes_project():
    data = _create_project()
    cid = data["course_id"]

    # Save the learner's implementation into the persistent workspace.
    res = client.put(
        f"/api/create-course/projects/{cid}/workspace",
        json={"files": [{"path": "main.py", "content": SOLUTION}]},
    )
    assert res.status_code == 200

    # Run the workspace — real sandbox execution.
    res = client.post(f"/api/create-course/projects/{cid}/run", json={})
    assert res.status_code == 200
    run = res.json()
    assert run["ran_ok"] is True
    assert "Counter" in run["stdout"]

    # NEXT verifies and (since learner did everything) completes the project.
    res = client.post(f"/api/create-course/projects/{cid}/next", json={})
    assert res.status_code == 200
    result = res.json()
    assert result["status"] == "project_complete"
    assert result["completed"] is True
    assert result["completion_percent"] == 100
    assert result["xp"] > 0

    # Idempotent: hitting NEXT again does not increase XP.
    xp = result["xp"]
    res2 = client.post(f"/api/create-course/projects/{cid}/next", json={})
    assert res2.json()["xp"] == xp


def test_incomplete_workspace_blocks_next_with_guidance():
    data = _create_project()
    cid = data["course_id"]
    # Only the setup file, no real implementation.
    client.put(
        f"/api/create-course/projects/{cid}/workspace",
        json={"files": [{"path": "main.py", "content": "# just a comment\n"}]},
    )
    res = client.post(f"/api/create-course/projects/{cid}/next", json={})
    body = res.json()
    assert body["status"] == "incomplete"
    assert body["completed"] is False
    assert body["feedback"]


def test_guidance_is_read_only_and_returns_microstep():
    data = _create_project()
    cid = data["course_id"]
    res = client.post(f"/api/create-course/projects/{cid}/guidance", json={"question": "how do I start?"})
    assert res.status_code == 200
    body = res.json()
    # Deterministic microstep always present; suggestion is optional.
    assert "action" in body

    # Guidance must not mutate the workspace.
    proj = client.get(f"/api/create-course/projects/{cid}").json()
    assert proj["completion_percent"] == 0


def test_resume_lists_project():
    data = _create_project()
    cid = data["course_id"]
    res = client.get("/api/create-course/projects")
    assert res.status_code == 200
    assert any(p["course_id"] == cid for p in res.json())


def test_project_feature_does_not_disturb_existing_courses():
    # Existing courses endpoint still works and returns native courses.
    res = client.get("/api/courses")
    assert res.status_code == 200
    ids = [c["id"] for c in res.json()]
    assert any(not i.startswith("project-") for i in ids)
