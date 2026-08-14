# -*- coding: utf-8 -*-
"""Server web del Durak: pagina webapp + WebSocket realtime + bot Telegram.

Avvio (senza token il bot è disabilitato e resta solo il server):
    BOT_TOKEN=... WEBAPP_URL=https://... .venv/Scripts/python.exe -m server.app
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import secrets
import time

from aiohttp import web

from .room import RoomManager

WEBAPP_DIR = pathlib.Path(__file__).resolve().parent.parent / "webapp"

# CORS per le API: la webapp statica (es. su Vercel) chiama /api/match da
# un'origine diversa. Di default aperto (il matchmaking è innocuo e protetto
# da token); in produzione si può restringere con CORS_ORIGINS (csv).
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response()
    else:
        resp = await handler(request)
    origin = request.headers.get("Origin")
    if origin and ("*" in CORS_ORIGINS or origin in CORS_ORIGINS):
        resp.headers["Access-Control-Allow-Origin"] = "*" if "*" in CORS_ORIGINS else origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Connessione WebSocket: ?m=<match>&t=<token> (multigiocatore) oppure
    ?demo=1&t=<token>&name=<nome>&seed=<seed> (demo contro l'IA)."""
    manager: RoomManager = request.app["manager"]
    q = request.query
    demo = q.get("demo") == "1"
    name = q.get("name", "Player")
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)

    if demo:
        token = q.get("t") or "demo"
        room = manager.get_or_create_demo(token, name, seed=int(q["seed"]) if q.get("seed") else None)
        idx = room.find_by_token(token)
    else:
        match_id = q.get("m", "")
        token = q.get("t", "")
        room = manager.get(match_id)
        idx = room.find_by_token(token) if room else None
        if room is None or idx is None:
            await ws.send_str('{"type":"error","text":"Partita non trovata: apri il gioco dal bot."}')
            await ws.close()
            return ws

    room.players[idx]["ws"] = ws
    room.saw_connection = True
    room.last_active = time.monotonic()
    room.start_if_needed()
    room.broadcast_state()

    try:
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue
            try:
                data = msg.json()
            except ValueError:
                continue
            await room.handle(ws, data, idx)
    finally:
        room.disconnect(idx)
        if room.demo:
            # la stanza demo vive finché il browser la tiene aperta
            pass
    return ws


async def api_match(request: web.Request) -> web.Response:
    """Crea/unisce una partita (matchmaking): ritorna {m, t, name}.
    Con `players` (2-6) crea una stanza MULTI con quel numero di posti
    (il creatore condivide il link; gli altri si uniscono con /api/join)."""
    manager: RoomManager = request.app["manager"]
    try:
        data = await request.json()
    except Exception:
        data = {}
    uid = data.get("uid") or secrets.token_urlsafe(12)
    name = str(data.get("name") or "Player")[:18]
    try:
        players = int(data.get("players") or 2)
    except (TypeError, ValueError):
        players = 2
    players = max(2, min(6, players))
    if players > 2:
        match_id, token = manager.create_room(str(uid), None, name, players)
    else:
        match_id, token = manager.register_human(str(uid), None, name)
    return web.json_response({"m": match_id, "t": token, "name": name})


async def api_join(request: web.Request) -> web.Response:
    """Un giocatore si unisce a una stanza esistente dal link di invito
    (?m=<match>&join=1): ritorna {m, t} o 404 se la stanza è piena/partita."""
    manager: RoomManager = request.app["manager"]
    try:
        data = await request.json()
    except Exception:
        data = {}
    match_id = str(data.get("m") or "")
    uid = data.get("uid") or secrets.token_urlsafe(12)
    name = str(data.get("name") or "Player")[:18]
    joined = manager.join_room(match_id, str(uid), None, name)
    if joined is None:
        return web.json_response({"error": "room not joinable"},
                                 status=404)
    m, t = joined
    return web.json_response({"m": m, "t": t, "name": name})


async def make_app() -> web.Application:
    manager = RoomManager()
    app = web.Application(middlewares=[cors_middleware])
    app["manager"] = manager
    app.router.add_get("/", lambda r: web.FileResponse(WEBAPP_DIR / "index.html"))
    app.router.add_get("/play", lambda r: web.FileResponse(WEBAPP_DIR / "index.html"))
    app.router.add_get("/ws", ws_handler)
    app.router.add_post("/api/match", api_match)
    app.router.add_post("/api/join", api_join)
    app.router.add_static("/static/", WEBAPP_DIR, show_index=False)
    return app


async def _webhook(request: web.Request, bot_app, Update):
    """Endpoint POST chiamato da Telegram: ogni richiesta è un update JSON."""
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return web.Response(status=200)


def main() -> None:
    import asyncio as _asyncio

    async def run() -> None:
        # carica .env (token, WEBAPP_URL, porta) come fa bot/main.py
        from bot.main import _load_env
        _load_env()
        app = await make_app()
        # bot Telegram (opzionale: serve BOT_TOKEN + WEBAPP_URL)
        bot_app = None
        token = os.environ.get("BOT_TOKEN")
        webapp_url = os.environ.get("WEBAPP_URL", "").rstrip("/")
        if token:
            from bot.main import build_bot
            bot_app = build_bot(token, webapp_url, app["manager"])
            await bot_app.initialize()
            # webhook (produzione su Render): Telegram chiama POST /webhook —
            # niente polling, niente conflitti, e il servizio si risveglia da
            # solo quando arriva un messaggio. RENDER_EXTERNAL_URL è iniettata
            # da Render; in locale si usa WEBHOOK_URL o si ripiega sul polling.
            webhook_url = os.environ.get("WEBHOOK_URL", "").rstrip("/")
            if not webhook_url:
                webhook_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
            if webhook_url:
                from telegram import Update
                url = webhook_url + "/webhook"
                await bot_app.bot.set_webhook(url)
                app.router.add_post("/webhook", lambda r: _webhook(r, bot_app, Update))
                await bot_app.start()
                print(f"[bot] webhook attivo su {url}")
            else:
                # fallback locale: MAI sabotare un webhook di produzione —
                # avviare il polling con un webhook attivo lo RIMUOVE e il
                # bot di produzione diventa sordo (capitato il 12/08)
                wh = await bot_app.bot.get_webhook_info()
                if wh.url:
                    print(f"[bot] webhook attivo su {wh.url}: "
                          "bot locale disabilitato")
                    await bot_app.shutdown()
                    bot_app = None
                else:
                    await bot_app.updater.start_polling()
                    await bot_app.start()
                    print(f"[bot] polling attivo con token {token[:8]}…")
        else:
            print("[bot] BOT_TOKEN assente: solo server web (demo: "
                  "http://localhost:8765/play?demo=1)")
        port = int(os.environ.get("PORT", "8765"))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"[server] in ascolto su http://0.0.0.0:{port}")
        try:
            await _asyncio.Event().wait()
        finally:
            if bot_app:
                await bot_app.stop()
                await bot_app.shutdown()

    _asyncio.run(run())


if __name__ == "__main__":
    main()
