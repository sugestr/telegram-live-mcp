"""Interactive sign-in runs only in the human's terminal, never through MCP."""
import argparse
import asyncio
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import auth, config


def save_credentials():
    root = config.private_dir(config.state_home())
    path = root / "credentials.json"
    if path.exists():
        return config.load()
    if not sys.stdin.isatty():
        raise SystemExit("Вход требует обычного Терминала. Не передавайте коды/пароли в чат Codex.")
    print("Получите собственные api_id и api_hash: https://my.telegram.org → API development tools.")
    api_id = input("API ID: ").strip()
    api_hash = getpass.getpass("API hash (не отображается): ").strip()
    if not api_id.isdigit() or int(api_id) <= 0 or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
        raise SystemExit("Неверный формат API ID/hash; данные не сохранены.")
    fd, temporary = tempfile.mkstemp(dir=root, prefix=".credentials-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"api_id": int(api_id), "api_hash": api_hash}, handle)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return config.load()


async def login(qr=True):
    if not sys.stdin.isatty():
        raise SystemExit("Запустите эту команду сами в Терминале: вход нельзя выполнить через MCP.")
    from telethon import TelegramClient
    from telethon.errors import AuthKeyDuplicatedError
    cfg = save_credentials()
    path = Path(cfg["session_path"])
    foreign = auth.foreign_session_host(path)
    if foreign:
        raise SystemExit("Сессия создана на другом компьютере. Используйте новый TELEGRAM_LIVE_HOME и войдите заново.")
    if path.exists() and not auth.session_host_file(path).is_file():
        raise SystemExit("У существующей сессии нет метки компьютера. Используйте новый TELEGRAM_LIVE_HOME и войдите заново.")
    auth.mark_session_host(path)
    client = TelegramClient(str(path), cfg["api_id"], cfg["api_hash"], receive_updates=False,
                            device_model="Telegram Live MCP", app_version="0.1.0")
    try:
        await client.connect()
        auth.secure_session(path)
        if not await client.is_user_authorized():
            if qr:
                import segno
                def render(url):
                    print("Telegram на телефоне → Настройки → Устройства → Подключить устройство.")
                    segno.make(url).terminal(compact=True)
                await auth.qr_login(client, render, session_path=path)
            else:
                await auth.interactive_login(client, session_path=path)
        me = await client.get_me()
        auth.mark_session_host(path)
        auth.secure_session(path)
        print("Вход выполнен: %s%s (id %s)." % (
            me.first_name or "", " (@%s)" % me.username if me.username else "", me.id))
        print("Состояние хранится только здесь: %s" % config.state_home())
    except AuthKeyDuplicatedError:
        raise SystemExit("Telegram отозвал скопированный ключ. Создайте новый TELEGRAM_LIVE_HOME и войдите на этом Mac.")
    finally:
        await client.disconnect()
        auth.secure_session(path)


def executable():
    return Path(sys.executable).absolute().with_name("telegram-live")


def codex_binary():
    found = shutil.which("codex")
    if found:
        return found
    candidates = [
        "/Applications/Codex.app/Contents/Resources/codex",
        "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
        "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
    ]
    return next((p for p in candidates if Path(p).is_file()), None)


def register_codex():
    binary = codex_binary()
    command = executable()
    if not command.is_file():
        raise SystemExit("Команда telegram-live не установлена; сначала выполните install.sh.")
    if not binary:
        print("В Codex добавьте локальный STDIO MCP командой: %s serve" % command)
        raise SystemExit("CLI codex не найден. Точная ручная настройка есть в README.md.")
    existing = subprocess.run([binary, "mcp", "get", "telegram-live", "--json"],
                              capture_output=True, text=True)
    if existing.returncode == 0:
        raise SystemExit("telegram-live уже зарегистрирован. Существующее подключение не заменено; проверьте его в Codex.")
    # Keep API credentials out of Codex configuration and command arguments.
    cmd = [binary, "mcp", "add", "telegram-live", "--env",
           "TELEGRAM_LIVE_HOME=%s" % config.state_home(), "--", str(command), "serve"]
    subprocess.run(cmd, check=True)
    print("Подключение добавлено. Перезапустите Codex и начните новый чат.")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(prog="telegram-live")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="Запустить локальный read-only MCP по STDIO")
    sign = sub.add_parser("login", help="Личный вход в Telegram в Терминале")
    sign.add_argument("--phone", action="store_true", help="Код вместо QR")
    sub.add_parser("register-codex", help="Добавить MCP в Codex; существующий не заменяется")
    sub.add_parser("paths", help="Показать пути без секретов")
    args = parser.parse_args()
    if args.command == "serve":
        from .server import main as serve
        serve()
    elif args.command == "login":
        asyncio.run(login(qr=not args.phone))
    elif args.command == "register-codex":
        register_codex()
    else:
        print(config.state_home())
