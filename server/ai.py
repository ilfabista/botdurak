# -*- coding: utf-8 -*-
"""Avversario automatico per la modalità demo e per gli stress test.

Strategia volutamente semplice (base):
- Attacco: carta più bassa non-briscola, altrimenti la più bassa.
- Difesa: la carta più bassa che batte (non-briscola preferita); se non può
  battere, trasferisce se ha una carta dello stesso valore dell'attacco
  aperto; altrimenti prende.
- Lancio: la carta stessa-valore più bassa; passa quando non può o deve.
"""
from __future__ import annotations

import random

from .game import (Game, MAX_PAIRS, RANK_ORDER, beats, rank, suit, lowest_card)


def choose_attack(game: Game, player: int) -> str | None:
    """Fase attack: la carta più bassa; a tavolo non vuoto solo carte
    stesso-valore del tavolo; None se non può giocare (chiude l'attacco)."""
    if not game.hands[player]:
        return None
    if not game.table:
        return lowest_card(game.hands[player], game.trump)
    if len(game.table_cards()) >= MAX_PAIRS * 2 - 1:
        return None                         # tavolo pieno
    ranks_ok = game.table_ranks()
    cands = [c for c in game.hands[player] if rank(c) in ranks_ok]
    if not cands:
        return None
    return min(cands, key=lambda c: RANK_ORDER[rank(c)])


def choose_throw_in(game: Game, player: int) -> str | None:
    """Fase throw_in: la carta stessa-valore più bassa, o None per passare."""
    if not game.hands[game.defender]:
        return None  # non si può attaccare un difensore senza carte
    if len(game.table_cards()) >= MAX_PAIRS * 2 - 1:
        return None                         # tavolo pieno
    ranks_ok = game.table_ranks()
    cands = [c for c in game.hands[player] if rank(c) in ranks_ok]
    if not cands:
        return None
    return min(cands, key=lambda c: RANK_ORDER[rank(c)])


def _cheapest_beating(game: Game, player: int, target: str) -> str | None:
    beats_ = [c for c in game.hands[player] if beats(c, target, game.trump)]
    if not beats_:
        return None
    non_trump = [c for c in beats_ if suit(c) != game.trump]
    pool = non_trump or beats_
    return min(pool, key=lambda c: RANK_ORDER[rank(c)])


def choose_defense(game: Game, player: int) -> dict:
    """Fase defend: {"action": "beat"|"transfer"|"take", "card": ...}."""
    target = game.open_card()
    if target is None:
        return {"action": "take"}
    card = _cheapest_beating(game, player, target)
    if card is not None:
        return {"action": "beat", "card": card}
    # non può battere: prova a trasferire (stesso valore dell'attacco aperto)
    if game.transfer_ranks(player) and len(game.table_cards()) < 12:
        r = game.transfer_ranks(player)[0]
        card = min((c for c in game.hands[player] if rank(c) == r),
                   key=lambda c: RANK_ORDER[rank(c)])
        return {"action": "transfer", "card": card}
    return {"action": "take"}


def choose_move(game: Game, player: int) -> dict:
    """Mossa completa per `player` secondo la fase corrente."""
    if game.phase == "attack":
        card = choose_attack(game, player)
        if card is None:
            return {"action": "pass"}   # chiude l'attacco (tavolo non vuoto)
        return {"action": "attack", "card": card}
    if game.phase == "throw_in":
        card = choose_throw_in(game, player)
        return {"action": "throw", "card": card} if card else {"action": "pass"}
    if game.phase == "defend":
        return choose_defense(game, player)
    return {"action": "none"}


def random_legal_move(game: Game, player: int, rng: random.Random) -> dict:
    """Mossa legale casuale — per stress test (non per la demo)."""
    if game.phase == "attack":
        if not game.table:
            return {"action": "attack", "card": rng.choice(game.hands[player])}
        if len(game.table_cards()) >= MAX_PAIRS * 2 - 1:
            return {"action": "pass"}
        cands = [c for c in game.hands[player] if rank(c) in game.table_ranks()]
        if cands and rng.random() < 0.7:
            return {"action": "attack", "card": rng.choice(cands)}
        return {"action": "pass"}
    if game.phase == "throw_in":
        if not game.hands[game.defender]:
            return {"action": "pass"}
        if len(game.table_cards()) >= MAX_PAIRS * 2 - 1:
            return {"action": "pass"}
        cands = [c for c in game.hands[player] if rank(c) in game.table_ranks()]
        if not cands:
            return {"action": "pass"}
        return {"action": "throw", "card": rng.choice(cands)}
    if game.phase == "defend":
        target = game.open_card()
        if target is None:
            return {"action": "take"}
        beating = [c for c in game.hands[player] if beats(c, target, game.trump)]
        if beating and rng.random() < 0.6:
            return {"action": "beat", "card": rng.choice(beating)}
        if game.transfer_ranks(player) and rng.random() < 0.3:
            r = game.transfer_ranks(player)[0]
            card = rng.choice([c for c in game.hands[player] if rank(c) == r])
            return {"action": "transfer", "card": card}
        return {"action": "take"}
    return {"action": "none"}


def apply_move(game: Game, player: int, move: dict) -> None:
    """Applica un dict-mossa a una partita (usato da server e test)."""
    action = move["action"]
    if action in ("attack", "throw"):
        game.play_attack(player, move["card"])
    elif action == "beat":
        game.play_defense(player, move["card"])
    elif action == "transfer":
        game.transfer(player, move["card"])
    elif action == "take":
        game.take(player)
    elif action == "pass":
        game.pass_turn(player)
    else:
        raise ValueError(f"mossa sconosciuta: {action}")
