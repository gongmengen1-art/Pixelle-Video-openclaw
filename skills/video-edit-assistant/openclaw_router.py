"""
openclaw Telegram 路由接入层

集成三件事：
  1. 判断消息是否应路由到 video-edit skill
  2. 下载 Telegram 附件到本地临时目录（图片/视频/音频）
  3. 调用 route_video_edit_message.py，用完清理临时文件

在 openclaw 的消息处理器里接入：

    # 同步
    from skills.video-edit-assistant.openclaw_router import handle_telegram_update
    result = handle_telegram_update(bot_token=TOKEN, update=update_dict)
    if result:
        bot.send_message(chat_id=..., text=result["reply_text"])

    # async (aiogram / python-telegram-bot v20+)
    from skills.video-edit-assistant.openclaw_router import handle_telegram_update_async
    result = await handle_telegram_update_async(bot_token=TOKEN, update=update_dict)
    if result:
        await message.reply_text(result["reply_text"])
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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

from workspace_cleaner import cleanup_temp_media
from session_bridge import has_active_session

TRIGGER_PREFIXES = ('/video-edit', '/video_edit', 'video-edit:', '视频剪辑：')
_TG_API = 'https://api.telegram.org'


# ---------------------------------------------------------------------------
# Telegram 附件下载
# ---------------------------------------------------------------------------

def download_telegram_files(
    bot_token: str,
    file_ids: list[str],
    dest_dir: str | Path | None = None,
) -> list[str]:
    """
    通过 Telegram Bot API 下载一批附件到本地。

    Parameters
    ----------
    bot_token : str
        Bot token，格式 "123456:ABC-xxx"
    file_ids : list[str]
        Telegram file_id 列表（来自 message.photo[-1].file_id、
        message.video.file_id、message.audio.file_id 等）
    dest_dir : str | Path | None
        下载目标目录；None 则自动创建临时目录（由调用方负责清理）

    Returns
    -------
    list[str]
        成功下载的本地文件路径列表
    """
    if not file_ids:
        return []

    dest = Path(dest_dir) if dest_dir else Path(tempfile.mkdtemp(prefix='tg_media_'))
    dest.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for fid in file_ids:
        try:
            # Step 1: getFile → 获取服务端路径
            get_file_url = f'{_TG_API}/bot{bot_token}/getFile?file_id={fid}'
            with urllib.request.urlopen(get_file_url, timeout=10) as r:
                info = json.loads(r.read())
            if not info.get('ok'):
                continue
            file_path = info['result']['file_path']          # e.g. photos/file_xxx.jpg
            filename = Path(file_path).name

            # Step 2: 下载文件内容
            download_url = f'{_TG_API}/file/bot{bot_token}/{file_path}'
            local = dest / filename
            urllib.request.urlretrieve(download_url, str(local))
            paths.append(str(local))
        except Exception:
            pass   # 单文件失败不影响其他文件

    return paths


def extract_file_ids(message: dict) -> list[str]:
    """
    从 Telegram message dict 中提取所有附件的 file_id。

    支持：photo、video、document、audio、voice、video_note。
    photo 取最高分辨率（列表最后一项）。
    """
    ids: list[str] = []

    if 'photo' in message:
        # photo 是按分辨率升序的数组，取最后一项（最大）
        ids.append(message['photo'][-1]['file_id'])

    for key in ('video', 'document', 'audio', 'voice', 'video_note'):
        if key in message:
            ids.append(message[key]['file_id'])

    return ids


# ---------------------------------------------------------------------------
# 触发判断
# ---------------------------------------------------------------------------

def is_video_edit_message(text: str, user_key: str | None = None) -> bool:
    """
    Return True when this message should be handled by the video-edit skill.

    Two cases:
    1. Message starts with a trigger prefix (/video-edit, video-edit:, 视频剪辑：)
    2. The user already has an active session — all replies should continue that flow
    """
    t = (text or '').strip()
    if any(t.startswith(p) for p in TRIGGER_PREFIXES):
        return True
    if user_key and has_active_session(user_key):
        return True
    return False


# ---------------------------------------------------------------------------
# 核心路由：同步版本
# ---------------------------------------------------------------------------

def handle_telegram_update(
    *,
    bot_token: str,
    update: dict,
    api_base: str | None = None,
    upload_oss: bool = True,
    python_executable: str | None = None,
) -> dict[str, Any] | None:
    """
    处理一条 Telegram Update。

    - 消息不匹配触发前缀时返回 None（不是本 skill 的消息）
    - 自动下载附件、调用 skill、清理临时文件
    - 返回 dict 一定包含 'reply_text' 字段

    Parameters
    ----------
    bot_token : str
        Telegram Bot Token
    update : dict
        来自 Telegram 的 Update 对象（已解析为 dict）
    api_base : str | None
        覆盖 config.yaml 的 api_base
    upload_oss : bool
        是否上传到 OSS
    python_executable : str | None
        Python 解释器路径，默认与当前进程相同
    """
    message = update.get('message') or update.get('edited_message', {})
    if not message:
        return None

    text = message.get('text') or message.get('caption') or ''
    user_id = str(message.get('from', {}).get('id', 'unknown'))
    user_key = f'tg:{user_id}'

    if not is_video_edit_message(text, user_key=user_key):
        return None

    # 下载附件
    file_ids = extract_file_ids(message)
    temp_dir = Path(tempfile.mkdtemp(prefix='tg_media_'))
    media_paths: list[str] = []
    if file_ids and bot_token:
        media_paths = download_telegram_files(bot_token, file_ids, dest_dir=temp_dir)

    try:
        result = _invoke_skill(
            user_id=user_id,
            text=text,
            media_paths=media_paths,
            api_base=api_base,
            upload_oss=upload_oss,
            python_executable=python_executable,
        )
    finally:
        # 无论成功与否，删除本次下载的临时媒体文件
        if media_paths:
            cleanup_temp_media(media_paths)
        _try_rmdir(temp_dir)

    return result


# ---------------------------------------------------------------------------
# 核心路由：async 版本
# ---------------------------------------------------------------------------

async def handle_telegram_update_async(
    *,
    bot_token: str,
    update: dict,
    api_base: str | None = None,
    upload_oss: bool = True,
) -> dict[str, Any] | None:
    """Async 版本，适用于 aiogram / python-telegram-bot v20+。"""
    import asyncio

    message = update.get('message') or update.get('edited_message', {})
    if not message:
        return None

    text = message.get('text') or message.get('caption') or ''
    user_id = str(message.get('from', {}).get('id', 'unknown'))
    user_key = f'tg:{user_id}'

    if not is_video_edit_message(text, user_key=user_key):
        return None

    file_ids = extract_file_ids(message)
    temp_dir = Path(tempfile.mkdtemp(prefix='tg_media_'))
    media_paths: list[str] = []
    if file_ids and bot_token:
        # 下载是网络 IO，用线程池避免阻塞事件循环
        loop = asyncio.get_event_loop()
        media_paths = await loop.run_in_executor(
            None,
            lambda: download_telegram_files(bot_token, file_ids, dest_dir=temp_dir),
        )

    try:
        python = sys.executable
        entry = str(_skill_dir / 'route_video_edit_message.py')
        cmd = [python, entry,
               '--user-key', f'tg:{user_id}',
               '--text', text]
        for p in media_paths:
            cmd += ['--media', p]
        if upload_oss:
            cmd.append('--upload-oss')
        if api_base:
            cmd += ['--api-base', api_base]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_project_root),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)

        if proc.returncode != 0:
            return {
                'state': 'error',
                'reply_text': f'视频剪辑服务异常，请稍后重试。\n（{stderr.decode()[-200:]}）',
            }
        return json.loads(stdout.decode())
    except asyncio.TimeoutError:
        return {'state': 'error', 'reply_text': '视频生成超时，请减少素材数量后重试。'}
    except Exception as exc:
        return {'state': 'error', 'reply_text': f'路由调用失败：{exc}'}
    finally:
        if media_paths:
            cleanup_temp_media(media_paths)
        _try_rmdir(temp_dir)


# ---------------------------------------------------------------------------
# 低层级接口（无 Telegram update 解析，给已提取好信息的调用方用）
# ---------------------------------------------------------------------------

def route_message(
    *,
    user_id: str,
    text: str,
    media_local_paths: list[str] | None = None,
    api_base: str | None = None,
    upload_oss: bool = True,
) -> dict[str, Any] | None:
    """
    已知 user_id / text / 本地文件路径时直接调用（无需 Telegram update 解析）。
    不做附件下载，也不清理传入的文件（由调用方负责）。
    返回 None 表示消息不匹配触发前缀。
    """
    if not is_video_edit_message(text, user_key=f'tg:{user_id}'):
        return None
    return _invoke_skill(
        user_id=user_id,
        text=text,
        media_paths=media_local_paths or [],
        api_base=api_base,
        upload_oss=upload_oss,
    )


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------

def _invoke_skill(
    *,
    user_id: str,
    text: str,
    media_paths: list[str],
    api_base: str | None,
    upload_oss: bool,
    python_executable: str | None = None,
) -> dict[str, Any]:
    python = python_executable or sys.executable
    entry = str(_skill_dir / 'route_video_edit_message.py')
    cmd = [python, entry, '--user-key', f'tg:{user_id}', '--text', text]
    for p in media_paths:
        cmd += ['--media', p]
    if upload_oss:
        cmd.append('--upload-oss')
    if api_base:
        cmd += ['--api-base', api_base]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(_project_root),
        )
        if proc.returncode != 0:
            return {
                'state': 'error',
                'reply_text': f'视频剪辑服务异常，请稍后重试。\n（{proc.stderr.strip()[-200:]}）',
                'error': proc.stderr,
            }
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return {'state': 'error', 'reply_text': '视频生成超时，请减少素材数量后重试。'}
    except Exception as exc:
        return {'state': 'error', 'reply_text': f'路由调用失败：{exc}'}


def _try_rmdir(path: Path) -> None:
    try:
        if path.exists() and not any(path.iterdir()):
            path.rmdir()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Smoke-test the openclaw router')
    parser.add_argument('--user-id', default='test_001')
    parser.add_argument('--text', default='/video-edit 帮我做个竖屏视频，文案：路由冒烟测试。')
    parser.add_argument('--media', action='append', default=[])
    parser.add_argument('--no-oss', action='store_true')
    args = parser.parse_args()

    print(f'is_video_edit_message: {is_video_edit_message(args.text)}')
    result = route_message(
        user_id=args.user_id,
        text=args.text,
        media_local_paths=args.media or None,
        upload_oss=not args.no_oss,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
