import getpass
import os
import socket
from pathlib import Path
from telethon.errors import PasswordHashInvalidError, PhoneCodeExpiredError, PhoneCodeInvalidError, SessionPasswordNeededError
MAX_ATTEMPTS = 3

def session_host_file(session_path):
    path = Path(str(session_path))
    if path.suffix == '.session':
        path = path.with_suffix('')
    return path.with_name(path.name + '.host')

def mark_session_host(session_path):
    target = session_host_file(session_path)
    target.write_text(socket.gethostname() + '\n', encoding='utf-8')
    os.chmod(str(target), 384)
    return target

def foreign_session_host(session_path):
    marker = session_host_file(session_path)
    try:
        issued = marker.read_text(encoding='utf-8').strip()
    except OSError:
        return ''
    return issued if issued and issued != socket.gethostname() else ''

def secure_session(session_path):
    if not session_path:
        return
    path = Path(str(session_path))
    if not path.suffix:
        path = path.with_suffix('.session')
    if path.exists():
        os.chmod(str(path), 384)

async def interactive_login(client, session_path=None, phone=None):
    await client.connect()
    secure_session(session_path)
    if await client.is_user_authorized():
        return await client.get_me()
    phone = phone or input('Номер телефона (в международном формате, +код страны…): ').strip()
    await client.send_code_request(phone)
    print('Код отправлен — ищи его в самом Telegram, сообщением от «Telegram», а не в SMS.')
    me = None
    for attempt in range(MAX_ATTEMPTS):
        code = input('Код из Telegram: ').strip()
        if not code:
            print('Пустой код — введи цифры из сообщения.')
            continue
        try:
            me = await client.sign_in(phone=phone, code=code)
            break
        except PhoneCodeInvalidError:
            print('Код неверный. Осталось попыток: %d' % (MAX_ATTEMPTS - attempt - 1))
        except PhoneCodeExpiredError:
            raise SystemExit('Код истёк. Запусти скрипт заново — придёт новый.')
        except SessionPasswordNeededError:
            me = await _password_login(client)
            break
    else:
        raise SystemExit('Слишком много неверных кодов. Попробуй позже.')
    secure_session(session_path)
    return me

async def qr_login(client, render, session_path=None, rounds=10):
    import asyncio
    await client.connect()
    secure_session(session_path)
    if await client.is_user_authorized():
        return await client.get_me()
    qr = await client.qr_login()
    for _ in range(rounds):
        render(qr.url)
        try:
            await qr.wait(timeout=60)
            break
        except asyncio.TimeoutError:
            await qr.recreate()
        except SessionPasswordNeededError:
            await _password_login(client)
            break
    else:
        raise SystemExit('QR не отсканирован. Запусти вход заново.')
    secure_session(session_path)
    return await client.get_me()

async def _password_login(client):
    print("Введите облачный пароль Telegram (2FA). При вводе символы не отображаются.")
    for _ in range(MAX_ATTEMPTS):
        password = getpass.getpass("Облачный пароль: ")
        if not password.strip():
            print("Пустой пароль; попытка входа не отправлена.")
            continue
        try:
            return await client.sign_in(password=password)
        except PasswordHashInvalidError:
            print("Пароль не подошёл.")
    raise SystemExit("Вход не завершён; повторите позже в Терминале.")
