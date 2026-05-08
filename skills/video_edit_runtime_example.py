import sys
from pathlib import Path

_skill_dir = Path(__file__).resolve().parent
_project_root = _skill_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from skills.video_edit_assistant_runtime import create_runtime


if __name__ == "__main__":
    runtime = create_runtime()

    step1 = runtime.ingest({"project_name": "brand-demo"}, aspect_ratio="9:16")
    print("STEP1", step1.summary)
    print(step1.questions)

    step2 = runtime.ingest({
        "script_text": "第一段文案\n第二段文案",
        "asset_paths": ["/tmp/demo1.mp4", "/tmp/demo2.mp4"],
    })
    print("STEP2", step2.summary)
    print(step2.payload)
