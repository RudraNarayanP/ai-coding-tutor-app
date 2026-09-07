"""Tests for Multi-Language Course Tracks (Python, Java, C++).

Covers:
- Loading all curriculums (Python, Java, C++)
- Multi-language course selection API
- Sandbox execution for Java and C++
"""

import asyncio
import httpx
import pytest

from backend.curriculum_loader import load_all_curriculums
from backend.lesson_engine import LessonEngine, ProgressionStore
from backend.sandbox import sandbox


def test_load_all_curriculums():
    curriculums = load_all_curriculums()
    assert "python" in curriculums
    assert "java" in curriculums
    assert "cpp" in curriculums

    assert len(curriculums["python"].lessons) >= 65
    assert len(curriculums["java"].lessons) >= 30
    assert len(curriculums["cpp"].lessons) >= 30


def test_java_sandbox_execution():
    code = """
public class Solution {
    public static int add(int a, int b) {
        return a + b;
    }
}
"""
    tests = [
        {"name": "test_add", "test_code": "if (Solution.add(3, 4) != 7) throw new AssertionError();", "required": True}
    ]
    payload = {"language": "java", "code": code, "tests": tests}
    res = asyncio.run(sandbox.run(payload))
    assert res["passed"] is True
    assert len(res["tests"]) == 1
    assert res["tests"][0]["passed"] is True


def test_cpp_sandbox_execution():
    code = """
int add(int a, int b) {
    return a + b;
}
"""
    tests = [
        {"name": "test_add", "test_code": "assert(add(3, 4) == 7);", "required": True}
    ]
    payload = {"language": "cpp", "code": code, "tests": tests}
    res = asyncio.run(sandbox.run(payload))
    assert res["passed"] is True
    assert len(res["tests"]) == 1
    assert res["tests"][0]["passed"] is True


def test_api_courses_endpoint():
    import backend.main as main
    transport = httpx.ASGITransport(app=main.app)
    async def call():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/courses")
            assert resp.status_code == 200
            data = resp.json()
            languages = [c["language"] for c in data]
            assert "python" in languages
            assert "java" in languages
            assert "cpp" in languages

            select_resp = await client.post("/api/courses/select", json={"language": "java"})
            assert select_resp.status_code == 200

            lessons_resp = await client.get("/api/lessons?language=java")
            assert lessons_resp.status_code == 200
            lessons_data = lessons_resp.json()
            assert len(lessons_data) >= 30
            assert lessons_data[0]["id"].startswith("java-")

            # Restore active language
            await client.post("/api/courses/select", json={"language": "python"})

    asyncio.run(call())
