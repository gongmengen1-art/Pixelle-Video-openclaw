from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_skill_dir = Path(__file__).resolve().parent
_project_root = _skill_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from skills.video_edit_assistant_adapter import run_video_edit_intake


def _load_json_arg(value: str | None) -> dict | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None

    potential_path = Path(value)
    if potential_path.exists() and potential_path.is_file():
        return json.loads(potential_path.read_text(encoding="utf-8"))

    return json.loads(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Video Edit Assistant intake CLI")
    parser.add_argument("--draft", help="Draft JSON string or path to JSON file", default=None)
    parser.add_argument("--patch", help="Patch JSON string or path to JSON file", default=None)
    parser.add_argument("--aspect-ratio", help="Aspect ratio like 9:16 / 16:9 / 1:1", default=None)
    parser.add_argument("--question-limit", type=int, default=3, help="Max follow-up questions to return")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")
    args = parser.parse_args()

    draft = _load_json_arg(args.draft)
    patch = _load_json_arg(args.patch)

    result = run_video_edit_intake(
        patch=patch,
        draft=draft,
        aspect_ratio=args.aspect_ratio,
        question_limit=args.question_limit,
    )

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
