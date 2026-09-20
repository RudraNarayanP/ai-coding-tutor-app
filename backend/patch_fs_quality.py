"""Fullstack course quality patch: verified sources (MDN, FastAPI, React docs,
Python docs) for all 20 lessons. All cited pages were fetched this session.

Run:  .venv/Scripts/python.exe backend/patch_fs_quality.py
"""
import json
from pathlib import Path

MOD = Path("curriculum/fullstack/modules")
PSF = "Python documentation license (PSF)"
MDN = "CC0 1.0 Universal (MDN Web Docs)"
OAI = "OpenAI API documentation (developers.openai.com)"
FASTAPI = "MIT (FastAPI documentation)"
REACT = "CC BY 4.0 (React documentation)"

def src(who, name, url, lic):
    return {"name": f"{who} — {name}", "url": url, "license": lic}

SOURCES: dict[str, dict] = {
    "fs-auth-header": src("FastAPI docs", "Security: 'a header Authorization with a value of Bearer plus the token'",
                          "https://fastapi.tiangolo.com/tutorial/security/first-steps/", FASTAPI),
    "fs-auth-store": src("FastAPI docs", "Security first steps — client-side bearer token flow",
                         "https://fastapi.tiangolo.com/tutorial/security/first-steps/", FASTAPI),
    "fs-auth-jwt-payload": src("FastAPI docs", "OAuth2 JWT — 'It is not encrypted, so, anyone could recover the information from the contents. But it's signed.'",
                               "https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/", FASTAPI),
    "fs-auth-expired": src("FastAPI docs", "OAuth2 JWT — signed token claims (sub/expiry)",
                           "https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/", FASTAPI),
    "fs-auth-checkpoint": src("FastAPI docs", "OAuth2 JWT — token expiry and re-login flow",
                              "https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/", FASTAPI),
    "fs-state-update": src("React docs", "Updating Objects in State — 'Instead of mutating them, you should always replace them.'",
                           "https://react.dev/learn/updating-objects-in-state", REACT),
    "fs-state-reducer": src("React docs", "useReducer — 'a React Hook that lets you add a reducer to your component'",
                            "https://react.dev/reference/react/useReducer", REACT),
    "fs-state-list": src("React docs", "Updating Objects and Arrays in State — immutable replacement",
                         "https://react.dev/learn/updating-objects-in-state", REACT),
    "fs-state-select": src("React docs", "Managing state with reducers — reading state for derived lists",
                           "https://react.dev/reference/react/useReducer", REACT),
    "fs-state-checkpoint": src("React docs", "useReducer — applying sequential actions",
                               "https://react.dev/reference/react/useReducer", REACT),
    "fs-url-join": src("Python docs", "String Methods — str.rstrip() / str.lstrip()",
                       "https://docs.python.org/3/library/stdtypes.html#string-methods", PSF),
    "fs-query-string": src("Python docs", "urllib.parse.quote — 'Replace special characters in string using the %xx escape.'",
                           "https://docs.python.org/3/library/urllib.parse.html", PSF),
    "fs-parse-json": src("MDN", "HTTP response status codes — 4xx client errors / 5xx server errors",
                         "https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status", MDN),
    "fs-headers": src("MDN", "HTTP Authorization request header",
                      "https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Authorization", MDN),
    "fs-http-checkpoint": src("Python docs", "json — JSON encoder and decoder (json.dumps request bodies)",
                              "https://docs.python.org/3/library/json.html", PSF),
    "fs-rest-get": src("MDN", "Glossary: REST — 'software architecture design constraints' with resource URLs",
                       "https://developer.mozilla.org/en-US/docs/Glossary/REST", MDN),
    "fs-rest-page": src("FastAPI docs", "Query params — pagination with 'skip=0 and limit=10'",
                        "https://fastapi.tiangolo.com/tutorial/query-params/", FASTAPI),
    "fs-rest-filter": src("Python docs", "5.1.3. List Comprehensions — filtering with conditions",
                          "https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions", PSF),
    "fs-rest-idempotent": src("MDN", "Glossary: Idempotent — 'the intended effect ... of making a single request is the same as the effect of making several identical requests'",
                              "https://developer.mozilla.org/en-US/docs/Glossary/Idempotent", MDN),
    "fs-rest-checkpoint": src("MDN", "HTTP response status codes — 'Responses are grouped in five classes'",
                              "https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status", MDN),
}


def main() -> int:
    touched = 0
    for path in sorted(MOD.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data["lessons"]:
            lid = lesson["id"]
            if lid in SOURCES and not (lesson.get("source") or {}).get("url"):
                lesson["source"] = SOURCES[lid]
                changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched += 1
    print(f"patched {touched} fullstack modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
