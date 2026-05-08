from __future__ import annotations

import argparse
import json
import sys
import urllib.request
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


def _post_json(url: str, payload: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="video-edit-assistant skill entry")
    parser.add_argument("--draft", default=None)
    parser.add_argument("--patch", default=None)
    parser.add_argument("--aspect-ratio", default=None)
    parser.add_argument("--question-limit", type=int, default=3)
    parser.add_argument("--execute", action="store_true", help="When ready=true, call the local API automatically")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011", help="Base URL for Pixelle-Video API")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    result = run_video_edit_intake(
        patch=_load_json_arg(args.patch),
        draft=_load_json_arg(args.draft),
        aspect_ratio=args.aspect_ratio,
        question_limit=args.question_limit,
    )

    if args.execute and result.get("ready") and result.get("payload"):
        api_url = args.api_base.rstrip("/") + "/api/video/scripted-asset-edit/sync"
        result["execution"] = {
            "api_url": api_url,
            "response": _post_json(api_url, result["payload"]),
        }

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
