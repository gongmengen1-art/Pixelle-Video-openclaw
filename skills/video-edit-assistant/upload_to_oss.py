from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import quote

# Legacy STS defaults — kept for backward compatibility
_DEFAULT_STS_PATH = Path('/home/xvibe/.sts')
_DEFAULT_BUCKET = '301-chinamobile'
_DEFAULT_ENDPOINT = 'oss-accelerate.aliyuncs.com'
_DEFAULT_PREFIX = 'openclaw/video-edit/'


def _load_config_oss() -> dict:
    """Read OSS credentials from config.yaml (AK/SK style)."""
    try:
        from skill_config import load_video_edit_config
        return load_video_edit_config().get('oss', {})
    except Exception:
        return {}


def _load_sts_file(sts_path) -> dict:
    """Read legacy STS temporary-credential file."""
    p = Path(sts_path)
    if not p.exists():
        raise FileNotFoundError(f'STS file not found: {p}')
    obj = json.loads(p.read_text(encoding='utf-8'))
    creds = obj.get('Credentials', obj)
    return {
        'access_key_id': creds['AccessKeyId'],
        'access_key_secret': creds['AccessKeySecret'],
        'security_token': creds.get('SecurityToken'),
        'bucket': obj.get('bucket', _DEFAULT_BUCKET),
        'endpoint': obj.get('endpoint', _DEFAULT_ENDPOINT),
        'prefix': obj.get('prefix', _DEFAULT_PREFIX),
    }


def build_public_url(bucket: str, endpoint: str, object_key: str) -> str:
    return f'https://{bucket}.{endpoint}/{quote(object_key, safe="/")}'


def upload_file_to_oss(
    local_path,
    object_key: str | None = None,
    *,
    sts_path=_DEFAULT_STS_PATH,
) -> dict:
    """
    Upload a local file to Alibaba Cloud OSS.

    Auth priority:
      1. AK/SK from config.yaml  video_edit.oss section  (permanent credentials)
      2. STS token file at sts_path                       (legacy / temporary)
    """
    import oss2

    local = Path(local_path)
    if not local.exists():
        raise FileNotFoundError(f'Local file not found: {local}')

    oss_cfg = _load_config_oss()

    if oss_cfg.get('access_key_id') and oss_cfg.get('access_key_secret') and oss_cfg.get('bucket'):
        cfg = {
            'access_key_id': oss_cfg['access_key_id'],
            'access_key_secret': oss_cfg['access_key_secret'],
            'bucket': oss_cfg['bucket'],
            'endpoint': oss_cfg.get('endpoint', _DEFAULT_ENDPOINT),
            'prefix': oss_cfg.get('prefix', _DEFAULT_PREFIX),
        }
        auth = oss2.Auth(cfg['access_key_id'], cfg['access_key_secret'])
    else:
        cfg = _load_sts_file(sts_path)
        auth = oss2.StsAuth(cfg['access_key_id'], cfg['access_key_secret'], cfg['security_token'])

    if object_key is None:
        object_key = f"{cfg['prefix']}{local.name}"

    bucket_obj = oss2.Bucket(auth, f"https://{cfg['endpoint']}", cfg['bucket'])

    headers = {}
    content_type, _ = mimetypes.guess_type(local.name)
    if content_type:
        headers['Content-Type'] = content_type

    result = bucket_obj.put_object_from_file(object_key, str(local), headers=headers)
    url = build_public_url(cfg['bucket'], cfg['endpoint'], object_key)
    return {
        'bucket': cfg['bucket'],
        'endpoint': cfg['endpoint'],
        'object_key': object_key,
        'url': url,
        'etag': getattr(result, 'etag', None),
        'status': getattr(result, 'status', None),
    }
