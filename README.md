# Patchwork: local coding tutor

A local-first Python tutor where the lesson engine, code execution, and AI tutor are separate concerns.

## Architecture

- `src/App.tsx`: lesson UI that consumes backend lesson and progression state.
- `backend/lesson_models.py`: typed lesson, test, result, and progression contracts.
- `curriculum/python/course.json` and `curriculum/python/modules/*.json`: version-controlled course, module, concept, prerequisite, lesson, and deterministic test content.
- `backend/curriculum_loader.py`: schema validation, reference validation, ordering, and circular-prerequisite detection.
- `backend/lessons.py`: startup-loaded curriculum compatibility exports.
- `backend/lesson_engine.py`: lesson loading, execution-service orchestration, completion, and unlock decisions.
- `backend/ai_provider.py`: local-only `AIProvider` protocol, Ollama implementation, configuration, and model health check.
- `backend/tutor_service.py`: session hint storage and response-policy validation above the provider.
- `backend/main.py`: FastAPI boundary with lesson/progression APIs and the typed tutor/health APIs.
- `backend/sandbox.py` creates one fresh Docker container per `/api/run`, streams a JSON execution contract over stdin, collects structured results, and force-removes the container.
- `sandbox/Dockerfile` contains only the sandbox runner. Student code is never copied from or mounted from a host directory.
- AI boundary: `/api/tutor` sends lesson context, code, results, session hints, and hint level to Ollama on `localhost` only.

Deterministic flow: `GET /api/lessons` and `GET /api/lessons/{id}` expose course data; `POST /api/lessons/{id}/run` sends code with the backend-owned tests to Docker, then returns test results and progression. `POST /api/run` remains a compatibility route for the current lesson. No lesson completion decision calls Ollama.

The UI remains usable when AI is toggled off or Ollama is unavailable. Ollama is not involved in test execution, deterministic grading, or progression.

## Run

Frontend:

```powershell
npm install
npm run dev
```

Backend in another terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Optional AI runtime:

```powershell
ollama pull llama3.1:8b
ollama serve
```

Optional configuration uses local environment variables:

```powershell
$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_MODEL = "llama3.1:8b"
$env:OLLAMA_TIMEOUT_SECONDS = "45"
```

The tutor endpoint is `POST /api/tutor`; health is available at `GET /api/health/ollama`. Tutor failures return a safe unavailable response. Responses containing complete code for ordinary hint requests are replaced with a level-appropriate hint. This is a policy guard, not a claim that an arbitrary local model can never produce unsafe text.

The browser UI is at `http://localhost:5173`. The backend and Docker daemon are required for deterministic execution; Ollama is optional and only used by the separate tutor endpoint. Lessons and grading continue to work when Ollama is completely stopped.

## Sandbox threat model

The sandbox uses Docker's `network=none`, a non-root UID, read-only root filesystem, a small writable `/tmp`, dropped capabilities, `no-new-privileges`, memory/CPU/PID/file-descriptor limits, a 3-second wall-clock limit, and bounded request/output sizes. Containers are created and removed for every execution. No Docker socket, host directory, host environment, or host secret is mounted.

This is defense in depth, not a perfect security boundary. Docker, the Linux kernel, the container runtime, and the backend host remain trusted computing-base dependencies. The backend process and Docker daemon must be protected, and production deployments should use a dedicated worker host, patched Docker Desktop/kernel versions, stronger syscall profiles, request authentication/rate limits, and separate test infrastructure for higher-risk code.
