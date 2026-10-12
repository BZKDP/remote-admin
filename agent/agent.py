"""
Remote Admin — агент для ПК сотрудника (Windows).
Прозрачный корпоративный агент: подключается к вашему серверу, даёт экран/управление/терминал.

Установка (см. README): pip install -r requirements.txt, задать RA_SERVER/RA_AGENT_KEY, поставить службой.
Запуск вручную для теста:
    set RA_SERVER=ws://<server-host>:8765
    set RA_AGENT_KEY=общий_ключ
    python agent.py
"""
import asyncio
import json
import os
import socket
import getpass
import platform
import uuid
import io

import websockets
import mss
from PIL import Image
from pynput.mouse import Controller as Mouse, Button
from pynput.keyboard import Controller as Keyboard, Key

DATA_DIR = os.path.join(os.environ.get("PROGRAMDATA", os.path.expanduser("~")), "RemoteAdmin")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")


def load_config():
    """Настройки: сначала переменные окружения, потом config.json рядом (для .exe-развёртывания)."""
    server = os.environ.get("RA_SERVER")
    key = os.environ.get("RA_AGENT_KEY")
    if not server or not key:
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            server = server or cfg.get("server")
            key = key or cfg.get("agent_key")
        except Exception:
            pass
    return (server or "ws://127.0.0.1:8765").rstrip("/"), (key or "changeme-agent")


SERVER, AGENT_KEY = load_config()

# стабильный id агента, чтобы ПК не «двоился» при переподключениях
ID_FILE = os.path.join(DATA_DIR, "agent_id")


def load_agent_id():
    try:
        os.makedirs(os.path.dirname(ID_FILE), exist_ok=True)
        if os.path.exists(ID_FILE):
            return open(ID_FILE).read().strip()
        aid = str(uuid.uuid4())
        open(ID_FILE, "w").write(aid)
        return aid
    except Exception:
        return str(uuid.uuid4())


mouse = Mouse()
keyboard = Keyboard()

SPECIAL_KEYS = {
    "Enter": Key.enter, "Backspace": Key.backspace, "Tab": Key.tab, "Escape": Key.esc,
    "ArrowUp": Key.up, "ArrowDown": Key.down, "ArrowLeft": Key.left, "ArrowRight": Key.right,
    "Delete": Key.delete, "Home": Key.home, "End": Key.end, "PageUp": Key.page_up,
    "PageDown": Key.page_down, "Control": Key.ctrl, "Alt": Key.alt, "Shift": Key.shift,
    "Meta": Key.cmd, " ": Key.space, "CapsLock": Key.caps_lock,
    "F1": Key.f1, "F2": Key.f2, "F3": Key.f3, "F4": Key.f4, "F5": Key.f5, "F6": Key.f6,
    "F7": Key.f7, "F8": Key.f8, "F9": Key.f9, "F10": Key.f10, "F11": Key.f11, "F12": Key.f12,
}


class Agent:
    def __init__(self, ws):
        self.ws = ws
        self.screen_task = None
        self.shell = None
        self.shell_reader = None

    # ---------- экран ----------
    async def screen_loop(self, fps, quality, scale):
        interval = 1.0 / max(1, fps)
        with mss.mss() as sct:
            mon = sct.monitors[1]  # основной монитор
            while True:
                shot = sct.grab(mon)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                if scale and scale < 1.0:
                    img = img.resize((int(img.width * scale), int(img.height * scale)))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                try:
                    await self.ws.send(buf.getvalue())
                except Exception:
                    return
                await asyncio.sleep(interval)

    def start_screen(self, fps, quality, scale):
        self.stop_screen()
        self.screen_task = asyncio.create_task(self.screen_loop(fps, quality, scale))

    def stop_screen(self):
        if self.screen_task:
            self.screen_task.cancel()
            self.screen_task = None

    # ---------- ввод ----------
    def handle_input(self, d):
        action = d.get("action")
        with mss.mss() as sct:
            mon = sct.monitors[1]
        W, H = mon["width"], mon["height"]
        ox, oy = mon["left"], mon["top"]
        if action in ("move", "down", "up", "click", "dblclick", "scroll"):
            if "x" in d and "y" in d:
                mouse.position = (ox + int(d["x"] * W), oy + int(d["y"] * H))
        btn = {"left": Button.left, "right": Button.right, "middle": Button.middle}.get(d.get("button", "left"), Button.left)
        if action == "move":
            pass
        elif action == "down":
            mouse.press(btn)
        elif action == "up":
            mouse.release(btn)
        elif action == "click":
            mouse.click(btn, 1)
        elif action == "dblclick":
            mouse.click(btn, 2)
        elif action == "scroll":
            mouse.scroll(0, int(d.get("dy", 0)))
        elif action == "key":
            self.handle_key(d.get("key"), d.get("down", True))

    def handle_key(self, key, down):
        if key is None:
            return
        k = SPECIAL_KEYS.get(key)
        if k is None and len(key) == 1:
            k = key
        if k is None:
            return
        if down:
            keyboard.press(k)
        else:
            keyboard.release(k)

    # ---------- терминал (persistent PowerShell) ----------
    async def ensure_shell(self):
        if self.shell and self.shell.returncode is None:
            return
        self.shell = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoLogo", "-NoProfile",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self.shell_reader = asyncio.create_task(self.read_shell())

    async def read_shell(self):
        try:
            while True:
                chunk = await self.shell.stdout.read(4096)
                if not chunk:
                    break
                await self.send_json({"type": "exec_out", "data": chunk.decode("utf-8", "replace")})
        except Exception:
            pass

    async def exec_cmd(self, cmd):
        await self.ensure_shell()
        try:
            self.shell.stdin.write((cmd + "\r\n").encode("utf-8"))
            await self.shell.stdin.drain()
        except Exception as e:
            await self.send_json({"type": "exec_out", "data": f"[shell error: {e}]\r\n"})

    # ---------- отправка ----------
    async def send_json(self, obj):
        try:
            await self.ws.send(json.dumps(obj))
        except Exception:
            pass

    # ---------- диспетчер ----------
    async def handle(self, raw):
        d = json.loads(raw)
        t = d.get("type")
        if t == "screen_start":
            self.start_screen(d.get("fps", 6), d.get("quality", 55), d.get("scale", 1.0))
        elif t == "screen_stop":
            self.stop_screen()
        elif t == "input":
            self.handle_input(d)
        elif t == "exec":
            await self.exec_cmd(d.get("cmd", ""))

    def cleanup(self):
        self.stop_screen()
        if self.shell and self.shell.returncode is None:
            try:
                self.shell.terminate()
            except Exception:
                pass


def system_info():
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "?"
    return {
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "os": f"{platform.system()} {platform.release()}",
        "ip": ip,
    }


async def run_once():
    agent_id = load_agent_id()
    url = SERVER + "/ws/agent"
    async with websockets.connect(url, max_size=16 * 1024 * 1024, ping_interval=20) as ws:
        await ws.send(json.dumps({
            "type": "register", "key": AGENT_KEY, "agent_id": agent_id, "info": system_info(),
        }))
        ack = json.loads(await ws.recv())
        if ack.get("type") == "error":
            print("auth failed:", ack)
            return
        print("registered as", ack.get("agent_id"))
        a = Agent(ws)
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue  # от админа файлы придут бинарно (v2)
                await a.handle(raw)
        finally:
            a.cleanup()


async def main():
    while True:
        try:
            await run_once()
        except Exception as e:
            print("disconnected:", e)
        await asyncio.sleep(5)  # автопереподключение


if __name__ == "__main__":
    asyncio.run(main())
