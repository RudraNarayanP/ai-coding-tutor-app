"""Flow-state reward economy: stamp per-type xp_reward + duration_minutes on
every lesson across all courses (see audit/FLOW_DESIGN.md).

learn=10/5m, practice=15/6m, challenge=25/8m, checkpoint=40/10m,
+5 XP for advanced challenge/checkpoint. Ids, order, and everything else are
untouched — this only tunes the pacing numbers the engine already reads
(lesson.xp_reward, lesson.duration_minutes).

Run:  .venv/Scripts/python.exe backend/patch_curriculum_flow_economy.py
"""
import json
from pathlib import Path

BY_TYPE = {
    "learn": (10, 5),
    "practice": (15, 6),
    "challenge": (25, 8),
    "checkpoint": (40, 10),
}


def main() -> int:
    touched = 0
    total = 0
    for path in sorted(Path("curriculum").glob("*/modules/*.json")):
        if "generated" in path.parts:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data.get("lessons", []):
            ltype = (lesson.get("type") or "learn").lower().strip()
            xp, dur = BY_TYPE.get(ltype, (10, 5))
            if lesson.get("difficulty") == "advanced" and ltype in ("challenge", "checkpoint"):
                xp += 5
            if lesson.get("xp_reward") != xp:
                lesson["xp_reward"] = xp
                changed = True
            if lesson.get("duration_minutes") != dur:
                lesson["duration_minutes"] = dur
                changed = True
            total += 1
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched += 1
    print(f"applied flow economy to {total} lessons across {touched} module files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
