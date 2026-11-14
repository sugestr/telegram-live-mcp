"""Local state belongs to this installation, never to the source repository."""
import json
import os
import re
from pathlib import Path


def state_home():
    return Path(os.environ.get(
        "TELEGRAM_LIVE_HOME",
        "~/Library/Application Support/Telegram Live MCP"
    )).expanduser().resolve()


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def load():
    root = private_dir(state_home())
    path = root / "credentials.json"
    if not path.is_file():
        raise RuntimeError("Сначала запустите telegram-live login в Терминале.")
    data = json.loads(path.read_text(encoding="utf-8"))
    api_id = int(data.get("api_id", 0))
    api_hash = str(data.get("api_hash", ""))
    if api_id <= 0 or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
        raise RuntimeError("Неверный формат API ID/hash; повторите telegram-live login.")
    os.chmod(path, 0o600)
    return {
        "api_id": api_id, "api_hash": api_hash,
        "session_path": str(root / "account.session"),
        "reader_session_path": str(root / "account.session"),
        "run_dir": str(private_dir(root / "run")),
        "log_dir": str(private_dir(root / "logs")),
    }
