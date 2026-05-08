from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_skill_dir = Path(__file__).resolve().parent
_project_root = _skill_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_skill_dir) not in sys.path:
    sys.path.insert(0, str(_skill_dir))

from message_bridge import handle_video_edit_message


def main() -> int:
    parser = argparse.ArgumentParser(description='Route a /video-edit style message through the bridge')
    parser.add_argument('--user-key', required=True)
    parser.add_argument('--text', required=True)
    parser.add_argument('--media', action='append', default=[])
    parser.add_argument('--api-base', default='http://127.0.0.1:8011')
    parser.add_argument('--upload-oss', action='store_true')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    result = handle_video_edit_message(
        user_key=args.user_key,
        text=args.text,
        media_paths=args.media or None,
        api_base=args.api_base,
        upload_oss=args.upload_oss,
    )

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
