from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import quote

import oss2

DEFAULT_STS_PATH = Path('/home/xvibe/.sts')
DEFAULT_BUCKET = '301-chinamobile'
DEFAULT_ENDPOINT = 'oss-accelerate.aliyuncs.com'
DEFAULT_PREFIX = 'openclaw/video-edit/'


def load_sts_config(sts_path: str | Path = DEFAULT_STS_PATH) -> dict:
    p = Path(sts_path)
    if not p.exists():
        raise FileNotFoundError(f'STS file not found: {p}')
    obj = json.loads(p.read_text(encoding='utf-8'))
    creds = obj.get('Credentials', obj)
    return {
        'access_key_id': creds['AccessKeyId'],
        'access_key_secret': creds['AccessKeySecret'],
        'security_token': creds['SecurityToken'],
        'bucket': obj.get('bucket', DEFAULT_BUCKET),
        'endpoint': obj.get('endpoint', DEFAULT_ENDPOINT),
        'prefix': obj.get('prefix', DEFAULT_PREFIX),
    }


def build_public_url(bucket: str, endpoint: str, object_key: str) -> str:
    object_key = quote(object_key, safe='/')
    return f'https://{bucket}.{endpoint}/{object_key}'


def upload_file_to_oss(local_path: str | Path, object_key: str | None = None, *, sts_path: str | Path = DEFAULT_STS_PATH) -> dict:
    cfg = load_sts_config(sts_path)
    local = Path(local_path)
    if not local.exists():
        raise FileNotFoundError(f'Local file not found: {local}')

    if object_key is None:
        object_key = f"{cfg['prefix']}{local.name}"

    auth = oss2.StsAuth(cfg['access_key_id'], cfg['access_key_secret'], cfg['security_token'])
    bucket = oss2.Bucket(auth, f'https://{cfg['endpoint']}', cfg['bucket'])

    headers = {}
    content_type, _ = mimetypes.guess_type(local.name)
    if content_type:
        headers['Content-Type'] = content_type

    result = bucket.put_object_from_file(object_key, str(local), headers=headers)
    url = build_public_url(cfg['bucket'], cfg['endpoint'], object_key)
    return {
        'bucket': cfg['bucket'],
        'endpoint': cfg['endpoint'],
        'object_key': object_key,
        'url': url,
        'etag': getattr(result, 'etag', None),
        'status': getattr(result, 'status', None),
    }
