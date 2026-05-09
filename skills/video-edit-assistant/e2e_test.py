#!/usr/bin/env python3
"""
End-to-end integration test: Telegram message → Pixelle-Video API → OSS → URL

Simulates the full chain without a real Telegram bot:
  message_bridge  →  session_bridge  →  video_edit intake
  →  POST /api/video/scripted-asset-edit/sync
  →  upload_to_oss  →  public URL

Usage examples
--------------
# Single-turn (all info in one message):
python e2e_test.py --asset /path/to/img.jpg

# Provide custom script text:
python e2e_test.py --asset img1.jpg --asset img2.jpg --text "产品功能介绍，简洁有力"

# Multi-turn simulation (3 turns):
python e2e_test.py --asset img.jpg --mode multi

# Skip OSS upload (dry-run to API only):
python e2e_test.py --asset img.jpg --no-oss

Prerequisites
-------------
1. Pixelle-Video API must be running:
     cd <project_root> && uv run python api/app.py
2. config.yaml must exist with video_edit.oss filled in (for OSS test)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

_skill_dir = Path(__file__).resolve().parent
_project_root = _skill_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_skill_dir) not in sys.path:
    sys.path.insert(0, str(_skill_dir))

from skill_config import load_video_edit_config
from message_bridge import handle_video_edit_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_api(api_base: str) -> bool:
    try:
        with urllib.request.urlopen(f"{api_base.rstrip('/')}/health", timeout=8) as r:
            return r.status == 200
    except Exception as exc:
        print(f"  health check error: {exc}")
        return False


def _run_turn(
    user_key: str,
    text: str,
    media_paths: list[str] | None,
    api_base: str,
    upload_oss: bool,
) -> dict[str, Any]:
    return handle_video_edit_message(
        user_key=user_key,
        text=text,
        media_paths=media_paths,
        api_base=api_base,
        upload_oss=upload_oss,
    )


def _print_turn(label: str, result: dict):
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")
    print(f"  state   : {result['state']}")
    print(f"  reply   : {result['reply_text']}")
    draft = result.get('draft') or {}
    filled = [k for k, v in draft.items() if v not in (None, '', [], {})]
    print(f"  draft   : {filled}")
    if result.get('execution'):
        ex = result['execution']
        resp = ex.get('response', {})
        print(f"  api_url : {ex.get('api_url')}")
        print(f"  video   : {resp.get('video_url')}")
        print(f"  duration: {resp.get('duration')}s  size: {resp.get('file_size')}B")
        if ex.get('oss'):
            print(f"  OSS URL : {ex['oss'].get('url')}")
        if ex.get('oss_skip_reason'):
            print(f"  OSS skip: {ex['oss_skip_reason']}")


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

def test_single_turn(cfg: dict, assets: list[str], script: str, upload_oss: bool) -> bool:
    """
    Provide script + assets + orientation in one message.
    With all required fields present the intake should fire immediately.
    """
    print("\n\n══════════════════════════════════════════════════════════")
    print("  TEST: single-turn (all required info in one message)")
    print("══════════════════════════════════════════════════════════")

    user_key = f"e2e_single_{int(time.time())}"
    text = f"/video-edit 帮我做一个30秒竖屏视频，文案：{script}"

    result = _run_turn(user_key, text, assets, cfg['api_base'], upload_oss)
    _print_turn("Turn 1 — trigger + script + assets + orientation", result)

    if result['state'] == 'executed':
        print("\n  [PASS] executed in 1 turn")
        return True

    # Still collecting — provide the remaining missing fields
    print("\n  [INFO] still collecting, sending confirmation turn …")
    result2 = _run_turn(user_key, "就用这些", None, cfg['api_base'], upload_oss)
    _print_turn("Turn 2 — confirm", result2)

    if result2['state'] == 'executed':
        print("\n  [PASS] executed in 2 turns")
        return True

    print(f"\n  [WARN] not executed after 2 turns")
    return False


def test_multi_turn(cfg: dict, assets: list[str], script: str, upload_oss: bool) -> bool:
    """
    Simulate a realistic 3-turn Telegram conversation:
      1. Vague trigger
      2. Script + orientation
      3. Assets  →  should fire
    """
    print("\n\n══════════════════════════════════════════════════════════")
    print("  TEST: multi-turn conversation (3 turns)")
    print("══════════════════════════════════════════════════════════")

    user_key = f"e2e_multi_{int(time.time())}"

    # Turn 1: vague trigger
    r1 = _run_turn(user_key, "/video-edit 帮我做个视频", None, cfg['api_base'], False)
    _print_turn("Turn 1 — vague trigger", r1)
    if r1['state'] != 'collecting':
        print(f"\n  [FAIL] expected collecting on turn 1, got: {r1['state']}")
        return False

    # Turn 2: script + orientation (no assets yet)
    r2 = _run_turn(user_key, f"竖屏，文案：{script}", None, cfg['api_base'], False)
    _print_turn("Turn 2 — script + orientation", r2)
    if r2['state'] != 'collecting':
        print(f"\n  [FAIL] expected still collecting on turn 2, got: {r2['state']}")
        return False

    # Turn 3: assets → should execute
    r3 = _run_turn(user_key, "素材发你", assets, cfg['api_base'], upload_oss)
    _print_turn("Turn 3 — assets (triggers execution)", r3)

    if r3['state'] == 'executed':
        print("\n  [PASS] executed in 3 turns")
        return True

    print(f"\n  [WARN] not executed after 3 turns")
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='E2E integration test for video-edit skill',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--asset', action='append', required=True, metavar='PATH',
                        help='Local asset path (image or video). Repeat for multiple files.')
    parser.add_argument('--text', default='这是一款功能强大的产品，使用简单，欢迎体验。',
                        help='Script text for the test video (default: generic placeholder)')
    parser.add_argument('--mode', choices=['single', 'multi', 'both'], default='single',
                        help='Test mode: single-turn, multi-turn, or both (default: single)')
    parser.add_argument('--no-oss', action='store_true',
                        help='Skip OSS upload step')
    parser.add_argument('--api-base', default=None,
                        help='Override api_base from config.yaml')
    args = parser.parse_args()

    # ── Load config ──────────────────────────────────────────────────────────
    cfg = load_video_edit_config()
    if args.api_base:
        cfg['api_base'] = args.api_base

    oss_cfg = cfg.get('oss', {})
    upload_oss = (
        not args.no_oss
        and bool(oss_cfg.get('access_key_id'))
        and bool(oss_cfg.get('bucket'))
    )

    print("Config:")
    print(f"  api_base    : {cfg['api_base']}")
    print(f"  session_dir : {cfg['session_dir']}")
    print(f"  output_base : {cfg['output_base']}")
    print(f"  default_bgm : {cfg['default_bgm']}")
    print(f"  oss bucket  : {oss_cfg.get('bucket') or '(not set — OSS upload disabled)'}")
    print(f"  upload_oss  : {upload_oss}")

    # ── Validate assets ───────────────────────────────────────────────────────
    assets: list[str] = []
    for raw in args.asset:
        p = Path(raw)
        if not p.exists():
            print(f"\n[ERROR] Asset not found: {raw}")
            return 1
        assets.append(str(p.resolve()))
    print(f"\nTest assets ({len(assets)}):")
    for a in assets:
        print(f"  {a}")

    # ── API health ────────────────────────────────────────────────────────────
    print(f"\nChecking API at {cfg['api_base']} …")
    if not _check_api(cfg['api_base']):
        print("[ERROR] API unreachable. Start it with:")
        print(f"  cd {_project_root}")
        print("  uv run python api/app.py")
        return 1
    print("[OK] API is healthy")

    # ── Run tests ─────────────────────────────────────────────────────────────
    results: list[bool] = []

    if args.mode in ('single', 'both'):
        results.append(test_single_turn(cfg, assets, args.text, upload_oss))

    if args.mode in ('multi', 'both'):
        results.append(test_multi_turn(cfg, assets, args.text, upload_oss))

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n\n══════════════════════════════════════════════════════════")
    passed = sum(results)
    total = len(results)
    status = "PASS" if passed == total else "FAIL"
    print(f"  RESULT: {status}  ({passed}/{total} tests passed)")
    print("══════════════════════════════════════════════════════════\n")

    return 0 if passed == total else 1


if __name__ == '__main__':
    raise SystemExit(main())
