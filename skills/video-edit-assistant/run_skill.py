from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_skill_dir = Path(__file__).resolve().parent
_project_root = _skill_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from skills.video_edit_assistant_adapter import run_video_edit_intake


def _load_json_arg(value: str | None):
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    p = Path(value)
    if p.exists() and p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="video-edit-assistant skill entry")
    parser.add_argument("--draft", default=None)
    parser.add_argument("--patch", default=None)
    parser.add_argument("--aspect-ratio", default=None)
    parser.add_argument("--question-limit", type=int, default=3)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    result = run_video_edit_intake(
        patch=_load_json_arg(args.patch),
        draft=_load_json_arg(args.draft),
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
