# -*- coding: utf-8 -*-
"""Smoke test end-to-end del multiplayer via WebSocket.

Serve il server avviato su :8000 (`.venv/Scripts/python.exe -m server.app`).
Due client si registrano via POST /api/match, si collegano in WS alla stessa
stanza e giocano partite complete attraverso la rete, decidendo le mosse solo
dalla vista pubblica (come farebbe il client JS). Verifica: coerenza delle
viste, completamento, vincitore univoco.

Esegue: .venv/Scripts/python.exe scripts/smoke_test.py [partite]
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys

import aiohttp

BASE = os.environ.get("SMOKE_BASE", "http://localhost:8000")
RANK_ORDER = {"6": 0, "7": 1, "8": 2, "9": 3, "T": 4, "J": 5, "Q": 6, "K": 7, "A": 8}

# dal dict-mossa (action) al protocollo WS del server (type)
TYPE_MAP = {"attack": "play", "throw": "play", "beat": "beat",
            "transfer": "transfer", "take": "take", "pass": "pass"}


def to_ws_payload(move: dict) -> dict:
    payload = {"type": TYPE_MAP[move["action"]]}
    if "card" in move:
        payload["card"] = move["card"]
    return payload


# ---- politiche di mossa che lavorano sulla vista pubblica (dict) ----

def table_cards(s):
    out = []
    for p in s["table"]:
        out.extend(p["stack"])
        if p["defense"]:
            out.append(p["defense"])
    return out


def move_from_state(s, rng, kind: str) -> dict:
    hand = s["hand"]
    trump = s["trump"]
    if s["phase"] == "attack":
        if s["table"]:
            # attacco multi-carta: solo carte stesso-valore del tavolo, altrimenti
            # si chiude l'attacco (pass)
            ranks = {c[0] for c in table_cards(s)}
            cands = [c for c in hand if c[0] in ranks]
            if not cands:
                return {"action": "pass"}
            card = min(cands, key=lambda c: (c[1] == trump, RANK_ORDER[c[0]]))
            return {"action": "attack", "card": card}
        card = min(hand, key=lambda c: (c[1] == trump, RANK_ORDER[c[0]]))
        return {"action": "attack", "card": card}
    if s["phase"] == "throw_in":
        ranks = {c[0] for c in table_cards(s)}
        cands = [c for c in hand if c[0] in ranks]
        if not cands:
            return {"action": "pass"}
        if kind == "random":
            return {"action": "throw", "card": rng.choice(cands)}
        return {"action": "throw", "card": min(cands, key=lambda c: RANK_ORDER[c[0]])}
    if s["phase"] == "defend":
        open_pair = next(p for p in s["table"] if p["open"])
        target = open_pair["stack"][-1]

        def beats(card, t):
            if card[1] == t[1]:
                return RANK_ORDER[card[0]] > RANK_ORDER[t[0]]
            return card[1] == trump

        beating = [c for c in hand if beats(c, target)]
        if beating and (kind == "ai" or rng.random() < 0.6):
            if kind == "ai":
                non_trump = [c for c in beating if c[1] != trump]
                card = min(non_trump or beating, key=lambda c: RANK_ORDER[c[0]])
            else:
                card = rng.choice(beating)
            return {"action": "beat", "card": card}
        if s["transfer_ranks"] and (kind == "ai" or rng.random() < 0.5):
            r = s["transfer_ranks"][0]
            card = rng.choice([c for c in hand if c[0] == r])
            return {"action": "transfer", "card": card}
        return {"action": "take"}
    return {"action": "none"}


class Client:
    def __init__(self, name, rng):
        self.name = name
        self.rng = rng
        self.ws = None
        self.state = None
        self.transfers = 0

    async def open(self, session):
        # uid unico per run: evita che user_room riusi stanze di run precedenti
        async with session.post(f"{BASE}/api/match",
                                json={"uid": f"{self.name}-{os.urandom(6).hex()}",
                                      "name": self.name}) as resp:
            info = await resp.json()
        self.ws = await session.ws_connect(
            f"{BASE}/ws?m={info['m']}&t={info['t']}&name={self.name}")

    async def recv_until_state(self, timeout=45):
        async def _loop():
            while True:
                msg = await self.ws.receive(timeout=timeout)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("type") == "state":
                        new = data["state"]
                        if (self.state and self.state["last_action"] == "transfer"
                                and new["last_action"] != "transfer"):
                            self.transfers += 1
                        self.state = new
                        return new
                    if data.get("type") in ("toast", "error"):
                        print(f"[{self.name}] {data.get('text')}", flush=True)
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    raise RuntimeError(f"{self.name}: connessione chiusa ({msg.type})")
        return await asyncio.wait_for(_loop(), timeout=timeout)

    async def send(self, obj):
        await self.ws.send_str(json.dumps(obj))

    def my_turn(self):
        s = self.state
        if s is None or s["phase"] == "over":
            return False
        if s["phase"] in ("attack", "throw_in"):
            return s["attacker"] == s["viewer"]
        return s["defender"] == s["viewer"]

    def fingerprint(self):
        s = self.state
        return (s["phase"], s["last_action"], len(s["table"]), s["deck_count"],
                tuple(s["hand"]), s["opp_count"])


async def wait_changed(c, timeout=45):
    """Attende il PROSSIMO stato diverso da quello attuale: una mossa
    rifiutata per race non produce broadcast, quindi si continua ad
    attendere finché il server non muove da solo o l'avversario agisce."""
    before = c.fingerprint()
    while True:
        s = await c.recv_until_state(timeout=timeout)
        if c.fingerprint() != before:
            return s


async def drain_pending(c):
    """Consuma i messaggi già in coda (senza attendere): vista fresca,
    meno mosse basate su stati stantii."""
    while True:
        try:
            m = await c.ws.receive(timeout=0.05)
            if m.type == aiohttp.WSMsgType.TEXT:
                d = json.loads(m.data)
                if d.get("type") == "state":
                    c.state = d["state"]
        except asyncio.TimeoutError:
            return


async def play_game(session, game_id, rng) -> dict:
    a = Client(f"A{game_id}", rng)
    b = Client(f"B{game_id}", rng)
    await a.open(session)
    await b.open(session)
    # il primo client può ricevere lo stato "lobby" prima della seconda
    # connessione: drena finché la partita non parte
    for c in (a, b):
        for _ in range(5):
            s = await c.recv_until_state()
            print(f"[{c.name}] stato: started={s['started']} phase={s['phase']} "
                  f"winner={s['winner']}", flush=True)
            if s["started"]:
                break
        assert c.state["started"], "stanza non avviata dopo due connessioni"

    rounds = 0
    while True:
        rounds += 1
        assert rounds < 600, "la partita non termina"
        mover = next((c for c in (a, b) if c.my_turn()), None)
        if mover is None:
            # entrambi devono consumare gli stati in coda
            await a.recv_until_state()
            await b.recv_until_state()
            continue
        kind = "ai" if mover.name.startswith("A") else "random"
        move = move_from_state(mover.state, rng, kind)
        await mover.send(to_ws_payload(move))
        await wait_changed(a)
        await wait_changed(b)
        await drain_pending(a)
        await drain_pending(b)
        if a.state["phase"] == "over":
            break

    # coerenza finale delle due viste
    assert a.state["winner"] == b.state["winner"]
    assert a.state["winner"] in (0, 1, -1)
    return {"winner": a.state["winner"], "transfers": a.transfers + b.transfers,
            "rounds": rounds, "deck": a.state["deck_count"]}


async def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    rng = random.Random(42)
    total_tr = 0
    async with aiohttp.ClientSession() as session:
        for i in range(n):
            res = await play_game(session, i, rng)
            total_tr += res["transfers"]
            print(f"partita {i}: vince {res['winner']} | "
                  f"trasferimenti={res['transfers']} | round={res['rounds']} | "
                  f"mazzo={res['deck']}")
    print(f"OK: {n} partite multiplayer via WebSocket "
          f"(trasferimenti totali: {total_tr})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
