#!/bin/bash
set -euo pipefail
umask 077
cd "$(dirname "$0")"
python_bin=""
for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
    python_bin="$(command -v "$candidate")"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  echo 'Нужен Python 3.10+. Например, установите Python с python.org или через Homebrew и повторите.' >&2
  exit 1
fi
"$python_bin" -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check .
echo
echo "Установлено. Войдите лично в обычном Терминале:"
printf '  %q login\n' "$PWD/.venv/bin/telegram-live"
echo "Затем добавьте подключение в Codex:"
printf '  %q register-codex\n' "$PWD/.venv/bin/telegram-live"
