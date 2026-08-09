# -*- coding: utf-8 -*-
"""Logica pura del Durak переводной (perevodnoy) 1v1 — nessuna dipendenza esterna.

Regole implementate:
- Mazzo da 36 (6..A, 4 semi); briscola = seme della carta in fondo al mazzo.
- 6 carte a testa; attacca chi ha la briscola più bassa (o la carta più bassa).
- Attacco: giocare una carta scoperta. Difesa: battere (stesso seme più alto,
  o briscola), trasferire (carta dello stesso valore dell'attacco aperto: si
  posa sopra come se battesse e DIVENTA lei l'attacco da battere; in 1v1
  l'attacco torna all'avversario, i ruoli si scambiano), o prendere tutto.
- Dopo una difesa riuscita l'attaccante può "lanciare" solo carte dello stesso
  valore di carte già sul tavolo, massimo 6 coppie (12 carte), e solo se il
  difensore ha almeno una carta in mano.
- Presa: chi prende raccoglie tutto; l'altro attacca il giro dopo.
- Giro pulito: chi ha difeso attacca il giro dopo.
- Quando il mazzo è finito, a fine giro vince chi non ha carte (se entrambi
  hanno carte si continua; entrambi a zero = pareggio, rarissimo).
"""
from __future__ import annotations

import random
from typing import Optional

SUITS = "HDCS"          # Cuori, Quadri, Fiori, Picche
SUIT_NAMES = {"H": "Cuori", "D": "Quadri", "C": "Fiori", "S": "Picche"}
RANKS = ["6", "7", "8", "9", "T", "J", "Q", "K", "A"]
RANK_ORDER = {r: i for i, r in enumerate(RANKS)}
MAX_PAIRS = 6           # massimo coppie attacco/risposta sul tavolo
HAND_SIZE = 6


def make_deck() -> list[str]:
    """Mazzo da 36: ["6H","6D","6C","6S", ... , "AH","AD","AC","AS"]."""
    return [r + s for s in SUITS for r in RANKS]


def rank(card: str) -> str:
    return card[0]


def suit(card: str) -> str:
    return card[1]


def beats(card: str, target: str, trump: str) -> bool:
    """True se `card` batte `target` (stesso seme più alto o briscola)."""
    if suit(card) == suit(target):
        return RANK_ORDER[rank(card)] > RANK_ORDER[rank(target)]
    return suit(card) == trump


def lowest_card(hand: list[str], trump: str) -> str:
    """Carta più bassa della mano (regola di attacco del banco/AI)."""
    return min(hand, key=lambda c: (suit(c) == trump, RANK_ORDER[rank(c)]))


class Game:
    """Partita di Durak переводной a 2 giocatori. Nessuna logica di rete.

    Convenzioni:
    - `players` = [0, 1]; `attacker`/`defender` indicano i ruoli correnti
      (si scambiano a ogni trasferimento).
    - `table` = lista di coppie {stack, defense, open, next_to, order}:
      `stack` = pila di carte stesso-valore (la prima è l'attacco originale,
      le successive sono trasferimenti); la carta in cima alla pila è
      l'attacco aperto da battere; `defense` = carta di risposta (chiude);
      `open` = True finché la coppia ha un attacco senza risposta.
      `next_to`/`order` servono solo al layout del client.
    - `phase`: "attack" (deve giocare l'attaccante), "defend" (deve rispondere
      il difensore), "throw_in" (l'attaccante può lanciare o passare),
      "over" (partita finita).
    - `winner`: indice del vincitore, -1 per pareggio, None se in corso.
    """

    def __init__(self, seed: Optional[int] = None, first_attacker: Optional[int] = None):
        self.rng = random.Random(seed)
        self.deck = make_deck()
        self.rng.shuffle(self.deck)
        # La briscola è il seme della carta in fondo al mazzo (l'ultima pescata).
        self.trump = self.deck[-1][1]
        self.hands: list[list[str]] = [[], []]
        for _ in range(HAND_SIZE):
            for p in (0, 1):
                self.hands[p].append(self.deck.pop(0))
        self.table: list[dict] = []
        self.discard: list[str] = []          # carte battute fuori dal gioco
        self.phase = "attack"
        self.winner: Optional[int] = None     # 0/1 vincitore, -1 pareggio
        self.last_action: str = ""            # per toast/client
        self._order_counter = 0

        if first_attacker is None:
            self.attacker = self._first_attacker()
        else:
            self.attacker = first_attacker
        self.defender = 1 - self.attacker

    # ------------------------------------------------------------- helpers

    def _first_attacker(self) -> int:
        def key(p: int) -> tuple:
            trumps = [c for c in self.hands[p] if suit(c) == self.trump]
            if trumps:
                return (0, RANK_ORDER[rank(min(trumps, key=lambda c: RANK_ORDER[rank(c)]))])
            return (1, min(RANK_ORDER[rank(c)] for c in self.hands[p]))
        return 0 if key(0) <= key(1) else 1

    def table_cards(self) -> list[str]:
        out = []
        for pair in self.table:
            out.extend(pair["stack"])
            if pair["defense"]:
                out.append(pair["defense"])
        return out

    def open_pairs(self) -> list[dict]:
        """Tutte le coppie con un attacco non ancora risposto."""
        return [p for p in self.table if p["open"]]

    def open_pair(self) -> Optional[dict]:
        """Prima coppia aperta (per ordine di gioco) — quella da battere."""
        for pair in self.table:
            if pair["open"]:
                return pair
        return None

    def open_card(self) -> Optional[str]:
        """Carta che il difensore deve battere (cima della pila aperta)."""
        pair = self.open_pair()
        return pair["stack"][-1] if pair else None

    def table_ranks(self) -> set[str]:
        """Valori di TUTTE le carte sul tavolo (per il lancio/attacco)."""
        return {rank(c) for c in self.table_cards()}

    def transfer_ranks(self, player: int) -> list[str]:
        """Valori che `player` può usare per trasferire l'attacco aperto.
        Solo con UN attacco aperto; MAI se l'avversario (che riceverebbe
        l'attacco) non ha carte in mano — non può difendere, e con il mazzo
        finito il trasferimento diventerebbe un ciclo infinito."""
        if self.phase != "defend" or player != self.defender:
            return []
        if len(self.open_pairs()) != 1:
            return []
        if not self.hands[1 - player]:
            return []
        if len(self.table_cards()) >= MAX_PAIRS * 2 - 1:
            return []                       # tavolo pieno: niente spazio per la risposta
        open_rank = rank(self.open_card()) if self.open_card() else None
        if open_rank is None:
            return []
        return [open_rank] if any(rank(c) == open_rank for c in self.hands[player]) else []

    def can_take(self, player: int) -> bool:
        return self.phase == "defend" and player == self.defender and bool(self.table)

    def can_pass(self, player: int) -> bool:
        if self.phase == "throw_in" and player == self.attacker:
            return True
        # in attack: chiudere un attacco multi-carta (premere «Fatto»)
        return self.phase == "attack" and player == self.attacker and bool(self.table)

    def _remove(self, player: int, card: str) -> None:
        try:
            self.hands[player].remove(card)
        except ValueError:
            raise ValueError(f"card {card} not in {player}'s hand")

    def _add_pair(self, card: str, next_to: Optional[int] = None) -> dict:
        self._order_counter += 1
        order = float(self._order_counter)
        if next_to is not None:
            # il trasferimento va disegnato accanto alla coppia che riprende
            order = self._sorted_table()[next_to]["order"] + 0.5
        pair = {"stack": [card], "defense": None, "open": True,
                "next_to": next_to, "order": order}
        self.table.append(pair)
        self.table.sort(key=lambda p: p["order"])
        return pair

    def _sorted_table(self) -> list[dict]:
        return sorted(self.table, key=lambda p: p["order"])

    # ------------------------------------------------------------- mosse

    def play_attack(self, player: int, card: str) -> None:
        """Attacco (fase attack, anche multi-carta) o lancio (throw_in).

        Regola переводной: all'inizio del proprio giro si possono giocare
        PIÙ carte dello stesso valore — la prima è libera (anche a tavolo
        vuoto: si entra con due 8), le successive devono avere un valore
        già presente sul tavolo (attacchi o risposte dell'avversario).
        Ogni carta è un attacco SEPARATO (coppia propria, affiancata) che
        il difensore deve battere singolarmente; se non batte tutto, prende.
        """
        if self.phase not in ("attack", "throw_in"):
            raise ValueError("not the moment to attack")
        if player != self.attacker:
            raise ValueError("not your turn to attack")
        if card not in self.hands[player]:
            raise ValueError("card not in hand")
        # massimo 6 coppie = 12 carte: un attacco deve lasciare lo spazio per
        # la risposta (a 11 carte il tavolo è pieno)
        if len(self.table_cards()) >= MAX_PAIRS * 2 - 1:
            raise ValueError("table full")

        if self.phase == "throw_in":
            if rank(card) not in self.table_ranks():
                raise ValueError("you can only throw cards of matching rank")
            if not self.hands[self.defender]:
                raise ValueError("the defender has no cards")
            self._remove(player, card)
            self._add_pair(card)
            self.last_action = "throw"
            self.phase = "defend"
        else:
            # fase attack: la prima carta è libera, le successive devono
            # avere un valore presente sul tavolo; mai contro un difensore
            # senza carte (come nel lancio)
            if self.table and rank(card) not in self.table_ranks():
                raise ValueError(
                    "you can only play cards matching a rank on the table")
            if self.table and not self.hands[self.defender]:
                raise ValueError("the defender has no cards")
            self._remove(player, card)
            self._add_pair(card)
            self.last_action = "attack"
            # resta in attack finché l'attaccante ha altre carte stesso-valore
            # da giocare; altrimenti l'attacco è chiuso e tocca al difensore
            if not any(rank(c) in self.table_ranks() for c in self.hands[player]):
                self.phase = "defend"

    def play_defense(self, player: int, card: str,
                     target: Optional[int] = None) -> None:
        """Risposta: battere un attacco aperto con una carta valida.

        `target` è l'indice della coppia da battere (usato dal giocatore
        quando ci sono più attacchi aperti, es. apertura multi-carta); se
        omesso, si batte la prima coppia aperta che la carta batte.
        Con più attacchi aperti la fase resta 'defend' finché non sono
        battuti tutti."""
        if self.phase != "defend" or player != self.defender:
            raise ValueError("not your turn to defend")
        if card not in self.hands[player]:
            raise ValueError("card not in hand")
        if target is not None:
            if not (0 <= target < len(self.table)):
                raise ValueError("no such pair on the table")
            pair = self.table[target]
            if not pair["open"]:
                raise ValueError("that pair is already beaten")
            if not beats(card, pair["stack"][-1], self.trump):
                raise ValueError("that card does not beat the attack")
        else:
            pair = None
            for p in self.open_pairs():
                if beats(card, p["stack"][-1], self.trump):
                    pair = p
                    break
            if pair is None:
                raise ValueError("that card beats no open attack")
        self._remove(player, card)
        pair["defense"] = card
        pair["open"] = False
        self.last_action = "beat"
        if self.open_pair() is None:
            self.phase = "throw_in"

    def transfer(self, player: int, card: str) -> None:
        """Trasferimento (перевод): carta dello stesso valore dell'attacco
        aperto. Si posa sulla pila come se la battesse e diventa lei l'attacco
        da battere. In 1v1 l'attacco torna all'avversario: i ruoli si scambiano
        e l'ex-attaccante deve difendere l'attacco trasferito."""
        if self.phase != "defend" or player != self.defender:
            raise ValueError("not your turn to defend")
        if card not in self.hands[player]:
            raise ValueError("card not in hand")
        if len(self.open_pairs()) != 1:
            raise ValueError("you can only transfer with a single open attack")
        if not self.hands[1 - player]:
            raise ValueError("your opponent has no cards: you cannot transfer")
        pair = self.open_pair()
        if pair is None:
            raise ValueError("no open attack")
        if rank(card) != rank(pair["stack"][-1]):
            raise ValueError("the card must match the attack rank")
        if len(self.table_cards()) >= MAX_PAIRS * 2 - 1:
            raise ValueError("table full")

        self._remove(player, card)
        pair["stack"].append(card)            # la carta nuova è l'attacco aperto
        self.last_action = "transfer"
        # i ruoli si scambiano: chi ha trasferito è al sicuro, l'ex-attaccante
        # ora deve difendere la carta trasferita
        self.attacker, self.defender = self.defender, self.attacker

    def take(self, player: int) -> None:
        """Il difensore si arrende e prende tutte le carte del tavolo."""
        if not self.can_take(player):
            raise ValueError("you cannot take now")
        self.hands[player].extend(self.table_cards())
        self.table.clear()
        self._order_counter = 0
        self.last_action = "take"
        # chi prende non cambia ruolo: l'attaccante attacca di nuovo
        self._resolve_round()

    def pass_turn(self, player: int) -> None:
        """In attack: chiude l'attacco multi-carta (tocca al difensore).
        In throw_in: tavolo pulito, le carte battute finiscono nello scarto e
        il difensore diventa attaccante."""
        if not self.can_pass(player):
            raise ValueError("you cannot pass now")
        if self.phase == "attack":
            self.last_action = "close_attack"
            self.phase = "defend"
            return
        for pair in self.table:
            self.discard.extend(pair["stack"])
            if pair["defense"]:
                self.discard.append(pair["defense"])
        self.table.clear()
        self._order_counter = 0
        self.last_action = "clear"
        self.attacker, self.defender = self.defender, self.attacker
        self._resolve_round()

    # ------------------------------------------------------------- giro

    def _resolve_round(self) -> None:
        """Pescata fino a 6 e controllo vittoria (solo qui si vince)."""
        for p in (self.attacker, self.defender):
            while self.deck and len(self.hands[p]) < HAND_SIZE:
                self.hands[p].append(self.deck.pop(0))
        self.phase = "attack"
        if self.winner is None and not self.deck:
            if not self.hands[self.attacker] and not self.hands[self.defender]:
                self.winner = -1               # pareggio (raro)
            elif not self.hands[self.attacker]:
                self.winner = self.attacker
            elif not self.hands[self.defender]:
                self.winner = self.defender
            if self.winner is not None:
                self.phase = "over"

    # ------------------------------------------------------------- vista

    def public_state(self, viewer: int) -> dict:
        """Stato da inviare a `viewer`: la mano dell'avversario è nascosta."""
        my_hand = sorted(self.hands[viewer], key=lambda c: (RANK_ORDER[rank(c)], c))
        return {
            "trump": self.trump,
            "deck_count": len(self.deck),
            # la briscola è l'ultima carta del mazzo: resta visibile (faccia
            # in su) finché non viene pescata
            "trump_card": self.deck[-1] if self.deck else None,
            "hand": my_hand,
            "opp_count": len(self.hands[1 - viewer]),
            "table": [dict(p) for p in self._sorted_table()],
            "attacker": self.attacker,
            "defender": self.defender,
            "viewer": viewer,
            "phase": self.phase,
            "can_take": self.can_take(viewer),
            "can_pass": self.can_pass(viewer),
            "transfer_ranks": self.transfer_ranks(viewer),
            "defender_empty": not self.hands[self.defender] if self.phase == "throw_in" else False,
            "winner": self.winner,
            "last_action": self.last_action,
        }
