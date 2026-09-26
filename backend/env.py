import os
from pathlib import Path


def _env_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def load_env_file() -> None:
    """Load project .env into os.environ. .env values take priority."""
    env_path = _env_path()
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def upsert_env_var(key: str, value: str) -> None:
    """Update or insert KEY=value in project .env and os.environ.

    Preserves unrelated lines/comments. Creates .env if missing.
    """
    key = (key or "").strip()
    if not key or "=" in key or any(ch.isspace() for ch in key):
        raise ValueError("invalid env key")
    value = "" if value is None else str(value).strip()
    os.environ[key] = value

    env_path = _env_path()
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    replaced = False
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("#") or "=" not in stripped:
            out.append(raw)
            continue
        existing_key = stripped.split("=", 1)[0].strip()
        if existing_key == key:
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(raw)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")

    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


load_env_file()
