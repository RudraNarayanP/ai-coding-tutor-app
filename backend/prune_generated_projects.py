"""Inspect and prune the guided-project store (`curriculum/generated/projects/`).

Why this exists: until the state-isolation fix, every backend test run created
real projects in the live store. The directory accumulated ~190 copies of the
test fixture's "Word Frequency Counter" project, and the Create Course screen
listed them all as resumable courses.

Default behaviour is a dry run - nothing is deleted unless you pass ``--apply``.

    # see what is in there
    python -m backend.prune_generated_projects

    # see what would go, keeping the 2 newest matches
    python -m backend.prune_generated_projects --title "Word Frequency Counter" --keep-newest 2

    # actually delete them
    python -m backend.prune_generated_projects --title "Word Frequency Counter" --keep-newest 2 --apply
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "curriculum" / "generated" / "projects"


def _records(store_dir: Path) -> list[dict]:
    out: list[dict] = []
    for path in sorted(store_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ! unreadable {path.name}: {exc}")
            continue
        data["_path"] = path
        data.setdefault("title", "(untitled)")
        data.setdefault("updated_at", path.stat().st_mtime)
        out.append(data)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="project store directory")
    parser.add_argument("--title", action="append", default=None, help="only prune projects with this exact title (repeatable)")
    parser.add_argument("--older-than-days", type=float, default=None, help="only prune matches updated before this cutoff")
    parser.add_argument("--keep-newest", type=int, default=0, help="retain the N most recently updated matches")
    parser.add_argument("--apply", action="store_true", help="delete the selected files (default: dry run)")
    args = parser.parse_args(argv)

    store_dir = args.dir.resolve()
    if not store_dir.is_dir():
        print(f"No project store at {store_dir}")
        return 1

    records = _records(store_dir)
    by_title: dict[str, list[dict]] = {}
    for rec in records:
        by_title.setdefault(rec["title"], []).append(rec)

    print(f"{store_dir}\n{len(records)} projects, {len(by_title)} distinct titles\n")
    for title, group in sorted(by_title.items(), key=lambda kv: -len(kv[1])):
        newest = max(g["updated_at"] for g in group)
        done = sum(1 for g in group if g.get("completed"))
        age = max(0.0, (time.time() - newest) / 86400.0)
        print(f"  {len(group):>4} x  {title[:58]:<58} completed={done:<4} newest={age:.1f}d ago")

    if not args.title:
        print("\nNothing selected - pass --title (repeatable) to choose what to prune.")
        return 0

    matches: list[dict] = []
    for title in args.title:
        matches.extend(by_title.get(title, []))
    if args.older_than_days is not None:
        cutoff = time.time() - args.older_than_days * 86400.0
        matches = [m for m in matches if m["updated_at"] < cutoff]

    matches.sort(key=lambda m: m["updated_at"], reverse=True)
    keep = matches[: max(0, args.keep_newest)]
    doomed = matches[len(keep):]

    print(f"\nSelected {len(matches)} match(es); keeping the newest {len(keep)}; "
          f"{len(doomed)} candidate(s) to delete.")
    for rec in doomed[:10]:
        print(f"  - {rec['_path'].name}  {rec['title'][:40]}")
    if len(doomed) > 10:
        print(f"  ... and {len(doomed) - 10} more")

    if not doomed:
        return 0
    if not args.apply:
        print("\nDRY RUN - add --apply to delete these files.")
        return 0

    removed = 0
    for rec in doomed:
        path: Path = rec["_path"]
        if store_dir not in path.resolve().parents:  # never delete outside the store
            print(f"  ! refusing to delete {path} (outside the store)")
            continue
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            print(f"  ! failed to delete {path.name}: {exc}")
    print(f"\nDeleted {removed} project file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
