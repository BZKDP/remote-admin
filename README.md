# Remote Admin

Self-hosted RMM для корпоративного парка Windows: экран сотрудника в реальном времени,
управление мышью/клавиатурой и терминал PowerShell. Только intranet, сервер и данные у вас.

## Архитектура
```
[Браузер-панель] ──► [Сервер relay + web (aiohttp)] ◄── [Агент на ПК] × N
```
- `server/` — relay и веб-панель (aiohttp, WebSocket). Держит список агентов и роутит кадры/команды админ↔агент.
- `agent/` — агент на ПК сотрудника (Python либо собранный .exe): захват экрана (mss+Pillow, JPEG),
  инъекция ввода (pynput), persistent PowerShell через stdin/stdout.
- `server/static/index.html` — панель: логин по паролю, список онлайн-ПК, экран на canvas, галка «управление», терминал, выбор качества.

## Возможности
- Трансляция экрана с регулируемым fps/сжатием/масштабом.
- Удалённые мышь и клавиатура (включая спец-клавиши и скролл).
- Интерактивный PowerShell на удалённой машине.
- Авторизация панели по паролю + короткоживущий токен сессии; агенты — по общему ключу.
- Автопереподключение агента, стабильный agent_id между перезапусками.

## Запуск сервера
```powershell
cd server
pip install -r requirements.txt
$env:RA_ADMIN_PASSWORD = "длинный-пароль-панели"
$env:RA_AGENT_KEY      = "общий-ключ-агентов"
python server.py   # панель на http://<host>:8765
```
Наружу не публиковать голым HTTP — только через reverse-proxy с TLS или защищённую сеть (тогда `wss://`).

## Агент
Запуск из исходника: `pip install -r agent/requirements.txt`, задать `RA_SERVER`/`RA_AGENT_KEY`, `python agent/agent.py`.
Настройки берутся из переменных окружения либо из `config.json` (см. `agent/config.example.json`).

## Сборка и подпись агента (опционально)
Скрипты в `build/` собирают `.exe` через PyInstaller и подписывают его self-signed code-signing сертификатом;
`installer/install_agent.ps1` ставит exe задачей автозапуска в сессии пользователя (Session 0 Isolation —
иначе экран/ввод не работают). Сам бинарь и приватный ключ (`.pfx`) в репозиторий не входят и не публикуются.

## Требования
Python 3.10+. Сервер: aiohttp. Агент: websockets, mss, Pillow, pynput. Сборка exe: PyInstaller (Windows).
