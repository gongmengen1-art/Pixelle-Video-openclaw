"""
工作区文件清理

清理三类文件，防止磁盘累积：
  1. 任务输出目录 output/{task_id}/   — OSS 上传成功后立即删除
  2. 过期任务目录                     — 定期扫描，删除超龄的（无论是否上传成功）
  3. 过期 session 文件                — 删除长时间没有活动的用户草稿
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import NamedTuple


class CleanupResult(NamedTuple):
    deleted: list[str]   # 成功删除的路径
    failed: list[str]    # 删除失败的路径（有日志）
    freed_bytes: int


# ---------------------------------------------------------------------------
# 1. 单个任务目录 — OSS 上传成功后立即调用
# ---------------------------------------------------------------------------

def cleanup_task_dir(task_dir: str | Path) -> CleanupResult:
    """
    删除单个任务输出目录（output/{task_id}/）。

    在 OSS 上传成功后立即调用，不保留任何中间文件。
    若目录不存在则静默返回（幂等）。
    """
    d = Path(task_dir)
    if not d.exists():
        return CleanupResult(deleted=[], failed=[], freed_bytes=0)

    freed = _dir_size(d)
    try:
        shutil.rmtree(d)
        return CleanupResult(deleted=[str(d)], failed=[], freed_bytes=freed)
    except Exception as exc:
        return CleanupResult(deleted=[], failed=[f'{d}: {exc}'], freed_bytes=0)


# ---------------------------------------------------------------------------
# 2. 过期任务目录 — 定期扫描，可注册为 cron / 后台线程
# ---------------------------------------------------------------------------

def cleanup_stale_tasks(
    output_base: str | Path,
    max_age_hours: float = 24,
) -> CleanupResult:
    """
    扫描 output/ 目录，删除最后修改时间超过 max_age_hours 的任务目录。

    任务目录名格式：YYYYMMDD_HHMMSS_xxxx
    只删目录，不动 output/.index.json 等根文件。

    推荐：每天执行一次，max_age_hours=24。
    """
    output_dir = Path(output_base) / 'output'
    if not output_dir.exists():
        return CleanupResult(deleted=[], failed=[], freed_bytes=0)

    cutoff = time.time() - max_age_hours * 3600
    deleted, failed, freed = [], [], 0

    for entry in output_dir.iterdir():
        if not entry.is_dir():
            continue
        # task_id 格式校验：8位日期_6位时间_4位随机
        name = entry.name
        if len(name) < 15 or not name[:8].isdigit():
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            size = _dir_size(entry)
            try:
                shutil.rmtree(entry)
                deleted.append(str(entry))
                freed += size
            except Exception as exc:
                failed.append(f'{entry}: {exc}')

    return CleanupResult(deleted=deleted, failed=failed, freed_bytes=freed)


# ---------------------------------------------------------------------------
# 3. 过期 session 文件 — 防止长期不活跃用户的草稿永久占磁盘
# ---------------------------------------------------------------------------

def cleanup_old_sessions(
    session_dir: str | Path,
    max_age_hours: float = 168,   # 默认 7 天
) -> CleanupResult:
    """
    删除 session_dir 下超过 max_age_hours 未更新的 .json 草稿文件。
    """
    d = Path(session_dir)
    if not d.exists():
        return CleanupResult(deleted=[], failed=[], freed_bytes=0)

    cutoff = time.time() - max_age_hours * 3600
    deleted, failed, freed = [], [], 0

    for f in d.glob('*.json'):
        try:
            if f.stat().st_mtime < cutoff:
                size = f.stat().st_size
                f.unlink()
                deleted.append(str(f))
                freed += size
        except Exception as exc:
            failed.append(f'{f}: {exc}')

    return CleanupResult(deleted=deleted, failed=failed, freed_bytes=freed)


# ---------------------------------------------------------------------------
# 4. 临时媒体文件 — openclaw 下载 Telegram 附件后用完清理
# ---------------------------------------------------------------------------

def cleanup_temp_media(paths: list[str] | list[Path]) -> CleanupResult:
    """
    删除一批临时文件（Telegram 下载的媒体文件）。
    路径可以是文件也可以是目录，文件不存在则跳过。
    """
    deleted, failed, freed = [], [], 0
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        size = path.stat().st_size if path.is_file() else _dir_size(path)
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted.append(str(path))
            freed += size
        except Exception as exc:
            failed.append(f'{path}: {exc}')
    return CleanupResult(deleted=deleted, failed=failed, freed_bytes=freed)


# ---------------------------------------------------------------------------
# 5. 全量清理入口 — 适合 cron / 启动时执行
# ---------------------------------------------------------------------------

def run_full_cleanup(
    output_base: str | Path,
    session_dir: str | Path,
    *,
    max_task_age_hours: float = 24,
    max_session_age_hours: float = 168,
) -> dict:
    """
    执行完整清理：过期任务目录 + 过期 session 文件。
    返回汇总报告，适合写日志。
    """
    task_result = cleanup_stale_tasks(output_base, max_age_hours=max_task_age_hours)
    sess_result = cleanup_old_sessions(session_dir, max_age_hours=max_session_age_hours)
    total_freed = task_result.freed_bytes + sess_result.freed_bytes
    return {
        'tasks_deleted': len(task_result.deleted),
        'tasks_failed': len(task_result.failed),
        'sessions_deleted': len(sess_result.deleted),
        'sessions_failed': len(sess_result.failed),
        'freed_bytes': total_freed,
        'freed_mb': round(total_freed / 1024 / 1024, 2),
        'details': {
            'tasks': task_result._asdict(),
            'sessions': sess_result._asdict(),
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())


# ---------------------------------------------------------------------------
# CLI — 手动触发清理 / cron 接入
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse, json, sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    parser = argparse.ArgumentParser(description='工作区文件清理')
    parser.add_argument('--output-base', default=None, help='Pixelle-Video 项目根目录')
    parser.add_argument('--session-dir', default=None, help='session 存储目录')
    parser.add_argument('--max-task-age-hours', type=float, default=24)
    parser.add_argument('--max-session-age-hours', type=float, default=168)
    parser.add_argument('--dry-run', action='store_true', help='只报告，不删除')
    args = parser.parse_args()

    from skill_config import load_video_edit_config
    cfg = load_video_edit_config()

    output_base = args.output_base or cfg['output_base']
    session_dir = args.session_dir or cfg['session_dir']

    if args.dry_run:
        # 报告会被删除的内容而不实际删除
        output_dir = Path(output_base) / 'output'
        cutoff = time.time() - args.max_task_age_hours * 3600
        stale = [
            str(e) for e in (output_dir.iterdir() if output_dir.exists() else [])
            if e.is_dir() and len(e.name) >= 15 and e.name[:8].isdigit()
            and e.stat().st_mtime < cutoff
        ]
        old_sessions = [
            str(f) for f in Path(session_dir).glob('*.json')
            if f.exists() and f.stat().st_mtime < time.time() - args.max_session_age_hours * 3600
        ] if Path(session_dir).exists() else []
        print(json.dumps({
            'dry_run': True,
            'stale_task_dirs': stale,
            'old_session_files': old_sessions,
        }, ensure_ascii=False, indent=2))
    else:
        report = run_full_cleanup(
            output_base=output_base,
            session_dir=session_dir,
            max_task_age_hours=args.max_task_age_hours,
            max_session_age_hours=args.max_session_age_hours,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
