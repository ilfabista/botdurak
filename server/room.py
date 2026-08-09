# -*- coding: utf-8 -*-
"""Gestione delle stanze di gioco: Room (stato + connessioni WS) e RoomManager
(matchmaking, pulizia, notifiche al bot). Nessuna dipendenza dal framework web:
app.py usa queste classi dentro gli handler aiohttp.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Optional

from .game import Game
from . import ai

TURN_TIME = 30.0            # secondi per mossa (epoch, confrontabile col client)
AI_DELAY = 0.9              # pausa "pensiero" dell'IA in modalità demo
AUTO_PASS_DELAY = 0.8       # attesa prima dell'auto-pass su difensore senza carte
ROOM_IDLE_MAX = 900         # 15 min senza attività → rimozione
ROOM_WAIT_MAX = 600         # 10 min in attesa del secondo giocatore
ROOM_JOIN_GRACE = 90.0      # finestra in cui una stanza mai connessa è joinabile


def sanitize_name(name: str, fallback: str = "Giocatore") -> str:
    name = (name or "").strip()[:18]
    return name or fallback


class Room:
    """Una partita: gioco + giocatori + connessioni + timer di turno."""

    def __init__(self, manager: "RoomManager", match_id: str, demo: bool = False,
                 seed: Optional[int] = None):
        self.manager = manager
        self.match_id = match_id
        self.demo = demo
        # quante connessioni umane servono per partire: 2 in multiplayer,
        # 1 in demo (il giocatore "IA" è un'entry fittizia senza ws)
        self.required_conns = 1 if demo else 2
        self.game = Game(seed=seed)
        self.players: dict[int, dict] = {}   # idx → {token, name, ws, chat_id}
        self.created_at = time.monotonic()
        self.last_active = time.monotonic()
        self.deadline: Optional[float] = None
        self.started = False
        self.abandoned = False
        self.saw_connection = False          # qualcuno si è mai connesso?
        self.task: Optional[asyncio.Task] = None

    # ------------------------------------------------------ giocatori

    def add_player(self, token: str, name: str, chat_id: Optional[int] = None) -> int:
        idx = len(self.players)
        self.players[idx] = {"token": token, "name": sanitize_name(name),
                             "ws": None, "chat_id": chat_id}
        return idx

    def find_by_token(self, token: str) -> Optional[int]:
        for idx, p in self.players.items():
            if p["token"] == token:
                return idx
        return None

    def all_connected(self) -> bool:
        return sum(1 for p in self.players.values() if p["ws"] is not None) >= self.required_conns

    def current_player(self) -> int:
        if self.game.phase in ("attack", "throw_in"):
            return self.game.attacker
        if self.game.phase == "defend":
            return self.game.defender
        return -1

    # ------------------------------------------------------ ciclo di gioco

    def start_if_needed(self) -> None:
        """Avvia il timer quando tutti i giocatori umani sono connessi."""
        if self.started or not self.all_connected():
            return
        self.started = True
        self.deadline = time.time() + TURN_TIME
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop_async())
        # notifica al bot (chat Telegram)
        chats = [p["chat_id"] for p in self.players.values() if p.get("chat_id")]
        if chats and self.manager.on_start:
            asyncio.create_task(self.manager.on_start(chats))

    async def _loop_async(self) -> None:
        try:
            while self.game.phase != "over" and not self.abandoned:
                self.last_active = time.monotonic()
                # l'IA in modalità demo muove da sola
                if self.demo and self.game.phase != "over" and self.current_player() == 1:
                    await asyncio.sleep(AI_DELAY)
                    if self.game.phase == "over":
                        break
                    move = ai.choose_move(self.game, 1)
                    try:
                        ai.apply_move(self.game, 1, move)
                        self._after_move()
                    except ValueError as e:
                        await self._toast(0, str(e))
                    continue
                # difensore senza carte in throw_in: l'attacco è impossibile,
                # l'attaccante passa d'ufficio (con un breve respiro per
                # evitare la race con un lancio appena inviato dal client)
                if (self.game.phase == "throw_in"
                        and not self.game.hands[self.game.defender]):
                    await asyncio.sleep(AUTO_PASS_DELAY)
                    if self.game.phase != "throw_in":
                        continue
                    self.game.pass_turn(self.game.attacker)
                    self._after_move()
                    continue
                # timeout: mossa automatica con la politica dell'IA
                if self.deadline and time.time() > self.deadline:
                    p = self.current_player()
                    move = ai.choose_move(self.game, p)
                    try:
                        ai.apply_move(self.game, p, move)
                        await self._toast(p, "⏱ Tempo scaduto: mossa automatica")
                        self._after_move()
                    except ValueError:
                        pass
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            pass

    def _after_move(self) -> None:
        """Dopo ogni mossa valida: nuovo deadline, stato trasmesso a tutti."""
        self.deadline = time.time() + TURN_TIME if self.game.phase != "over" else None
        self.broadcast_state()

    # ------------------------------------------------------ messaggi

    async def handle(self, ws, data: dict, idx: int) -> None:
        """Gestisce un messaggio WS di un giocatore."""
        self.last_active = time.monotonic()
        if self.abandoned or self.game.phase == "over":
            if data.get("type") == "rematch":
                self.rematch()
            return
        t = data.get("type")
        try:
            if t == "play":
                self.game.play_attack(idx, data["card"])
            elif t == "beat":
                self.game.play_defense(idx, data["card"])
            elif t == "transfer":
                self.game.transfer(idx, data["card"])
            elif t == "take":
                self.game.take(idx)
            elif t == "pass":
                self.game.pass_turn(idx)
            elif t == "rematch":
                self.rematch()
            elif t == "ping":
                return
            else:
                raise ValueError("comando sconosciuto")
            self._after_move()
        except ValueError as e:
            await self._toast(idx, f"⚠️ {e}")

    def rematch(self) -> None:
        """Nuova partita nella stessa stanza (solo a partita finita)."""
        if self.game.phase != "over" or self.abandoned:
            return
        self.game = Game(seed=None)
        self.deadline = time.time() + TURN_TIME
        self.broadcast_state()

    def disconnect(self, idx: int) -> None:
        """Un giocatore chiude la connessione: se la partita è in corso,
        l'avversario vince per abbandono."""
        p = self.players.get(idx)
        if p:
            p["ws"] = None
        if self.game.phase != "over" and not self.demo and self.started:
            self.abandoned = True
            self.game.winner = 1 - idx
            self.game.phase = "over"
            self.deadline = None
            self.broadcast_state()

    # ------------------------------------------------------ trasmissione

    def state_for(self, idx: int) -> dict:
        s = self.game.public_state(idx)
        s["my_name"] = self.players.get(idx, {}).get("name", "?")
        s["opp_name"] = self.players.get(1 - idx, {}).get("name", "IA")
        s["demo"] = self.demo
        s["started"] = self.started
        s["abandoned"] = self.abandoned
        s["deadline"] = self.deadline
        return s

    def broadcast_state(self) -> None:
        for idx, p in list(self.players.items()):
            if p["ws"] is not None:
                asyncio.create_task(self._send(idx, {"type": "state", "state": self.state_for(idx)}))

    async def _send(self, idx: int, payload: dict) -> None:
        ws = self.players[idx]["ws"]
        if ws is None or ws.closed:
            return
        try:
            await ws.send_str(json.dumps(payload))
        except (ConnectionError, RuntimeError):
            pass

    async def _toast(self, idx: int, text: str) -> None:
        await self._send(idx, {"type": "toast", "text": text})


class RoomManager:
    """Registro delle stanze + matchmaking per il bot."""

    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.user_room: dict[int, tuple[str, str]] = {}   # user_id → (match_id, token)
        self.on_start = None                              # callback bot (async, chat_ids)
        self._gc_task = None                              # avviato lazy (serve un loop)

    def _ensure_gc(self) -> None:
        """Avvia il garbage collector delle stanze (richiede un event loop;
        senza loop attivo la pulizia è semplicemente rimandata)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._gc_task is None or self._gc_task.done():
            self._gc_task = asyncio.create_task(self._gc_loop())

    # ------------------------------------------------------ creazione/join

    def register_human(self, user_id: int, chat_id: int, name: str) -> tuple[str, str]:
        """Matchmaking: entra in una stanza in attesa o ne crea una nuova.
        Ritorna (match_id, token)."""
        self._ensure_gc()
        # già in una stanza attiva?
        if user_id in self.user_room:
            match_id, token = self.user_room[user_id]
            room = self.rooms.get(match_id)
            if room and room.find_by_token(token) is not None:
                return match_id, token
            del self.user_room[user_id]
        # stanza in attesa: joinabile se il proprietario si è connesso almeno
        # una volta oppure la stanza è giovane (finestra di grazia per chi ha
        # appena premuto /durak e sta aprendo la webapp). Una stanza mai
        # connessa blocca la coda solo per ROOM_JOIN_GRACE.
        for match_id, room in self.rooms.items():
            owner_ok = room.saw_connection or \
                time.monotonic() - room.created_at < ROOM_JOIN_GRACE
            if (room.demo or room.started or len(room.players) != 1
                    or not owner_ok
                    or time.monotonic() - room.created_at > ROOM_WAIT_MAX):
                continue
            token = secrets.token_urlsafe(16)
            room.add_player(token, name, chat_id=chat_id)
            self.user_room[user_id] = (match_id, token)
            return match_id, token
        # nuova stanza
        match_id = secrets.token_urlsafe(8)
        room = Room(self, match_id)
        token = secrets.token_urlsafe(16)
        room.add_player(token, name, chat_id=chat_id)
        self.rooms[match_id] = room
        self.user_room[user_id] = (match_id, token)
        return match_id, token

    def get_or_create_demo(self, token: str, name: str, seed=None) -> Room:
        """Una stanza demo per token (permette di rientrare con lo stesso URL)."""
        self._ensure_gc()
        for room in self.rooms.values():
            if room.demo and room.find_by_token(token) is not None:
                return room
        match_id = "demo-" + secrets.token_urlsafe(8)
        room = Room(self, match_id, demo=True, seed=seed)
        room.add_player(token, sanitize_name(name, "Tu"), chat_id=None)
        room.add_player("ai", "IA", chat_id=None)   # giocatore fittizio
        self.rooms[match_id] = room
        return room

    def get(self, match_id: str) -> Optional[Room]:
        return self.rooms.get(match_id)

    # ------------------------------------------------------ pulizia

    async def _gc_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(60)
                now = time.monotonic()
                stale = []
                for match_id, room in self.rooms.items():
                    idle = now - room.last_active
                    waiting = not room.started and len(room.players) < 2
                    if idle > ROOM_IDLE_MAX or (waiting and now - room.created_at > ROOM_WAIT_MAX):
                        stale.append(match_id)
                for m in stale:
                    room = self.rooms.pop(m, None)
                    if room and room.task:
                        room.task.cancel()
        except asyncio.CancelledError:
            pass
