"""
Remote Admin — сервер-релей + веб-панель.
Корпоративный RMM: агенты на ПК сотрудников подключаются сюда, ты управляешь из браузера.

Запуск:
    pip install -r requirements.txt
    set RA_ADMIN_PASSWORD=твой_пароль_панели
    set RA_AGENT_KEY=общий_ключ_агентов
    python server.py

По умолчанию слушает 0.0.0.0:8765 (HTTP/WS). Для внешнего доступа — за Caddy/Tailscale с TLS.
"""
import asyncio
import json
import os
import secrets
import time
import uuid
from aiohttp import web, WSMsgType

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

ADMIN_PASSWORD = os.environ.get("RA_ADMIN_PASSWORD", "changeme")
AGENT_KEY = os.environ.get("RA_AGENT_KEY", "changeme-agent")
PORT = int(os.environ.get("RA_PORT", "8765"))

# id агента -> {"ws", "info", "viewers": set(admin_ws), "last": ts}
AGENTS: dict[str, dict] = {}
# admin ws -> {"attached": agent_id | None}
ADMINS: dict[web.WebSocketResponse, dict] = {}
# короткоживущие токены сессии панели
SESSIONS: dict[str, float] = {}


def agent_list_payload():
    return {
        "type": "agents",
        "list": [
            {
                "id": aid,
                "hostname": a["info"].get("hostname", "?"),
                "user": a["info"].get("user", "?"),
                "os": a["info"].get("os", "?"),
                "ip": a["info"].get("ip", "?"),
                "viewers": len(a["viewers"]),
                "since": a.get("since", 0),
            }
            for aid, a in AGENTS.items()
        ],
    }


async def broadcast_agents():
    msg = json.dumps(agent_list_payload())
    for ws in list(ADMINS.keys()):
        try:
            await ws.send_str(msg)
        except Exception:
            pass


# ---------- HTTP ----------
async def index(request):
    return web.FileResponse(os.path.join(STATIC, "index.html"))


async def login(request):
    data = await request.json()
    if secrets.compare_digest(data.get("password", ""), ADMIN_PASSWORD):
        token = secrets.token_urlsafe(24)
        SESSIONS[token] = time.time()
        return web.json_response({"ok": True, "token": token})
    return web.json_response({"ok": False}, status=401)


def valid_token(token: str) -> bool:
    ts = SESSIONS.get(token)
    if not ts:
        return False
    if time.time() - ts > 12 * 3600:
        SESSIONS.pop(token, None)
        return False
    return True


# ---------- WS: агент ----------
async def ws_agent(request):
    ws = web.WebSocketResponse(max_msg_size=16 * 1024 * 1024, heartbeat=30)
    await ws.prepare(request)

    peer_ip = request.headers.get("X-Forwarded-For", request.remote or "?").split(",")[0].strip()
    agent_id = None
    try:
        # первый кадр — регистрация
        first = await ws.receive()
        if first.type != WSMsgType.TEXT:
            await ws.close()
            return ws
        reg = json.loads(first.data)
        if reg.get("type") != "register" or not secrets.compare_digest(reg.get("key", ""), AGENT_KEY):
            await ws.send_str(json.dumps({"type": "error", "msg": "auth"}))
            await ws.close()
            return ws

        info = reg.get("info", {})
        info["ip"] = peer_ip
        agent_id = reg.get("agent_id") or str(uuid.uuid4())
        AGENTS[agent_id] = {"ws": ws, "info": info, "viewers": set(), "since": time.time()}
        await ws.send_str(json.dumps({"type": "registered", "agent_id": agent_id}))
        await broadcast_agents()

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                # данные от агента -> его зрителям (админам)
                for adm in list(AGENTS[agent_id]["viewers"]):
                    try:
                        await adm.send_str(msg.data)
                    except Exception:
                        pass
            elif msg.type == WSMsgType.BINARY:
                # кадры экрана / файлы -> зрителям
                for adm in list(AGENTS[agent_id]["viewers"]):
                    try:
                        await adm.send_bytes(msg.data)
                    except Exception:
                        pass
            elif msg.type == WSMsgType.ERROR:
                break
    except Exception as e:
        print("agent ws error:", e)
    finally:
        if agent_id and agent_id in AGENTS:
            for adm in AGENTS[agent_id]["viewers"]:
                if adm in ADMINS:
                    ADMINS[adm]["attached"] = None
                    try:
                        await adm.send_str(json.dumps({"type": "agent_gone", "id": agent_id}))
                    except Exception:
                        pass
            AGENTS.pop(agent_id, None)
            await broadcast_agents()
    return ws


# ---------- WS: админ ----------
async def ws_admin(request):
    ws = web.WebSocketResponse(max_msg_size=16 * 1024 * 1024, heartbeat=30)
    await ws.prepare(request)

    token = request.query.get("token", "")
    if not valid_token(token):
        await ws.send_str(json.dumps({"type": "error", "msg": "unauthorized"}))
        await ws.close()
        return ws

    ADMINS[ws] = {"attached": None}
    await ws.send_str(json.dumps(agent_list_payload()))

    def detach():
        aid = ADMINS[ws]["attached"]
        if aid and aid in AGENTS:
            AGENTS[aid]["viewers"].discard(ws)
        ADMINS[ws]["attached"] = None

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                t = data.get("type")
                if t == "attach":
                    detach()
                    aid = data.get("id")
                    if aid in AGENTS:
                        AGENTS[aid]["viewers"].add(ws)
                        ADMINS[ws]["attached"] = aid
                        await broadcast_agents()
                elif t == "detach":
                    detach()
                    await broadcast_agents()
                else:
                    # команда -> прикреплённому агенту
                    aid = ADMINS[ws]["attached"]
                    if aid and aid in AGENTS:
                        try:
                            await AGENTS[aid]["ws"].send_str(msg.data)
                        except Exception:
                            pass
            elif msg.type == WSMsgType.BINARY:
                aid = ADMINS[ws]["attached"]
                if aid and aid in AGENTS:
                    try:
                        await AGENTS[aid]["ws"].send_bytes(msg.data)
                    except Exception:
                        pass
            elif msg.type == WSMsgType.ERROR:
                break
    except Exception as e:
        print("admin ws error:", e)
    finally:
        detach()
        ADMINS.pop(ws, None)
        await broadcast_agents()
    return ws


def make_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/api/login", login)
    app.router.add_get("/ws/agent", ws_agent)
    app.router.add_get("/ws/admin", ws_admin)
    app.router.add_static("/static/", STATIC)
    return app


if __name__ == "__main__":
    if ADMIN_PASSWORD == "changeme" or AGENT_KEY == "changeme-agent":
        print("!! ВНИМАНИЕ: заданы дефолтные пароли. Установи RA_ADMIN_PASSWORD и RA_AGENT_KEY.")
    print(f"Remote Admin server на :{PORT}")
    web.run_app(make_app(), host="0.0.0.0", port=PORT)
