import json
import logging
import os
import tempfile
import time
from pathlib import Path
from telegram_live_mcp.config import state_home
ROOT = state_home() / 'transcripts'
MAX_TEXT = 20000
log = logging.getLogger('voice_cache')

def _path(chat_id, message_id, root=None):
    (chat_id, message_id) = (int(chat_id), int(message_id))
    if not chat_id or message_id <= 0:
        raise ValueError('voice cache key')
    return Path(root or ROOT) / str(chat_id) / ('%d.json' % message_id)

def get(chat_id, message_id, root=None):
    try:
        data = json.loads(_path(chat_id, message_id, root).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    text = str(data.get('text') or '').strip() if isinstance(data, dict) else ''
    return text or None

def put(chat_id, message_id, text, model='', root=None):
    text = str(text or '').strip()[:MAX_TEXT]
    if not text:
        return False
    return _write(chat_id, message_id, {'text': text, 'model': str(model or ''), 'at': int(time.time())}, root)

def put_failure(chat_id, message_id, reason, root=None):
    if get(chat_id, message_id, root):
        return False
    return _write(chat_id, message_id, {'text': '', 'failed': str(reason or 'unknown')[:200], 'at': int(time.time())}, root)

def failed(chat_id, message_id, root=None):
    try:
        data = json.loads(_path(chat_id, message_id, root).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or str(data.get('text') or '').strip():
        return None
    return str(data.get('failed') or '').strip() or None

def _write(chat_id, message_id, payload, root=None):
    try:
        target = _path(chat_id, message_id, root)
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent, delete=False, prefix='.tmp-', suffix='.json')
        with handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.chmod(handle.name, 0o600)
        os.replace(handle.name, target)
        return True
    except (OSError, ValueError, TypeError) as exc:
        log.warning('voice cache put skipped: %s', exc.__class__.__name__)
        try:
            os.unlink(handle.name)
        except (OSError, NameError, UnboundLocalError):
            pass
        return False
