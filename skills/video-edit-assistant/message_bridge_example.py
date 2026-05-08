from __future__ import annotations

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


if __name__ == '__main__':
    r1 = handle_video_edit_message(
        user_key='telegram-7217243523',
        text='/video-edit 帮我做一个 30 秒竖屏产品介绍视频',
    )
    print(json.dumps(r1, ensure_ascii=False, indent=2))
