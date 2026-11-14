import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
log = logging.getLogger('transcribe')
from telegram_live_mcp.config import state_home
MODELS = (os.environ.get('TELEGRAM_LIVE_WHISPER_MODEL', str(state_home() / 'models' / 'ggml-large-v3-turbo.bin')),)
VAD_MODEL = 'ggml-silero-v5.1.2.bin'
MAX_SECONDS = 1800
TIMEOUT_SEC = 40

def find_model():
    for candidate in MODELS:
        path = Path(os.path.expanduser(candidate))
        if path.exists():
            return path
    return None

def _cache_path(audio):
    stamp = hashlib.sha1(('%s:%d' % (audio, audio.stat().st_size)).encode('utf-8')).hexdigest()[:12]
    return audio.with_suffix(audio.suffix + '.%s.txt' % stamp)

def available():
    return bool(find_model() and (shutil.which('whisper-cli') or Path('/opt/homebrew/bin/whisper-cli').exists()))

def transcribe(audio_path, language=None, cache_key=None):
    if cache_key:
        from telegram_live_mcp import voice_cache
        cached = voice_cache.get(*cache_key)
        if cached:
            return (cached, None)
    (text, why_not) = _transcribe_file(audio_path, language)
    if text and cache_key:
        from telegram_live_mcp import voice_cache
        model = find_model()
        voice_cache.put(*cache_key, text, model=model.name if model else '')
    return (text, why_not)

def _transcribe_file(audio_path, language=None):
    audio = Path(audio_path)
    if not audio.exists():
        return (None, 'файла нет: %s' % audio)
    cache = _cache_path(audio)
    if cache.exists():
        return (cache.read_text(encoding='utf-8').strip(), None)
    binary = shutil.which('whisper-cli') or '/opt/homebrew/bin/whisper-cli'
    if not Path(binary).exists():
        return (None, 'нет whisper-cli (brew install whisper-cpp)')
    model = find_model()
    if model is None:
        return (None, 'не найдено ни одной модели whisper: искали в %s' % ', '.join(MODELS))
    wav = audio.with_suffix('.16k.wav')
    try:
        convert = subprocess.run(['ffmpeg', '-nostdin', '-y', '-i', str(audio), '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(wav)], capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        wav.unlink(missing_ok=True)
        return None, "ffmpeg отсутствует или конвертация превысила10секунд; аудио сохранено."
    if convert.returncode != 0:
        return (None, 'ffmpeg не смог прочитать файл: %s' % convert.stderr.decode('utf-8', 'replace')[-200:])
    threads = str(max(1, min(4, (os.cpu_count() or 2) // 2)))
    nice = [shutil.which('nice'), '-n', '19'] if shutil.which('nice') else []
    cmd = nice + [binary, '-m', str(model), '-f', str(wav), '-nt', '-np', '-l', language or 'auto', '-t', threads]
    vad = Path(model).parent / VAD_MODEL
    if vad.is_file():
        cmd += ['--vad', '-vm', str(vad)]
    try:
        run = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        wav.unlink(missing_ok=True)
        return (None, 'расшифровка не уложилась в %d секунд' % TIMEOUT_SEC)
    wav.unlink(missing_ok=True)
    if run.returncode != 0:
        return (None, 'whisper-cli не отработал: %s' % run.stderr.decode('utf-8', 'replace')[-200:])
    text = run.stdout.decode('utf-8', 'replace').strip()
    if not text:
        return (None, 'модель не услышала речи')
    cache.write_text(text, encoding='utf-8')
    return (text, None)
