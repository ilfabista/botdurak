# -*- coding: utf-8 -*-
"""Logica pura del Durak переводной (perevodnoy) per 2-6 giocatori — nessuna
dipendenza esterna.

Regole implementate:
- Mazzo da 36 (6..A, 4 semi); briscola = seme della carta in fondo al mazzo.
- 6 carte a testa; attacca chi ha la briscola più bassa (o la carta più bassa).
- Attacco: giocare una carta scoperta. Difesa: battere (stesso seme più alto,
  o briscola), trasferire (carta dello stesso valore dell'attacco aperto: si
  posa accanto e DIVENTA lei l'attacco corrente), o prendere tutto.
- Con 3+ giocatori (подкидной): dopo una difesa riuscita TUTTI gli altri
  giocatori, a turno in senso orario a partire dall'attaccante, possono
  \"lanciare\" carte dello stesso valore di carte già sul tavolo, o passare.
  Quando tutti hanno passato il giro si chiude. Massimo 6 coppie (12 carte).
- Trasferimento: l'attacco passa al giocatore SUCCESSIVO in senso orario
  (con 2 giocatori torna all'attaccante, i ruoli si scambiano).
- Presa: chi prende raccoglie tutto e NON attacca: attacca il successivo del
  difensore (con 2 giocatori riattacca l'attaccante).
- Giro pulito: chi ha difeso attacca il giro dopo.
- Quando il mazzo è finito, a fine giro chi resta senza carte esce dal gioco
  (ha vinto); quando resta un solo giocatore con carte, è il \"durak\" e la
  partita finisce. Con 2 giocatori: chi finisce le carte vince.
- Varianti переводной: niente trasferimento nel primo giro; non si può
  trasferire se una carta dell'attacco è già stata battuta; non si può
  trasferire a chi non ha carte.
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
MAX_PLAYERS = 6         # 36 carte / 6 a testa


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
    """Partita di Durak переводной a 2-6 giocatori. Nessuna logica di rete.

    Convenzioni:
    - `players` = [0 .. n_players-1] in senso orario; `attacker`/`defender`
      indicano i ruoli correnti (il trasferimento sposta l'attacco sul
      giocatore successivo; con 2 giocatori i ruoli si scambiano).
    - `table` = lista di coppie {stack, defense, open, next_to, order}:
      `stack` = pila di carte stesso-valore (la prima è l'attacco originale,
      le successive sono trasferimenti); ogni carta dello stack è un attacco
      SEPARATO da battere (regola reale); `defense` = carta di risposta
      (chiude la coppia); `open` = True finché la coppia ha un attacco senza
      risposta. `next_to`/`order` servono solo al layout del client.
    - `phase`: "attack" (deve giocare l'attaccante), "defend" (deve rispondere
      il difensore), "throw_in" (i giocatori lanciano o passano a turno,
      `thrower` = chi sta lanciando ora), "over" (partita finita).
    - `winner`: indice dell'ultimo giocatore uscito (vincitore), -1 pareggio,
      None se in corso; `out`: giocatori usciti (mani vuote, mazzo finito).
    """

    def __init__(self, seed: Optional[int] = None, n_players: int = 2,
                 first_attacker: Optional[int] = None):
        if not (2 <= n_players <= MAX_PLAYERS):
            raise ValueError("players must be between 2 and 6")
        self.n_players = n_players
        self.rng = random.Random(seed)
        self.deck = make_deck()
        self.rng.shuffle(self.deck)
        # La briscola è il seme della carta in fondo al mazzo (l'ultima pescata).
        self.trump = self.deck[-1][1]
        self.hands: list[list[str]] = [[] for _ in range(n_players)]
        for _ in range(HAND_SIZE):
            for p in range(n_players):
                self.hands[p].append(self.deck.pop(0))
        self.table: list[dict] = []
        self.discard: list[str] = []          # carte battute fuori dal gioco
        self.phase = "attack"
        self.winner: Optional[int] = None     # vincitore / -1 pareggio
        self.out: list[int] = []              # giocatori usciti (mani vuote)
        self.last_action: str = ""            # per toast/client
        self.first_round = True               # regola переводной: niente transfer al primo giro
        self.thrower: Optional[int] = None    # in throw_in: chi sta lanciando
        self.pass_count = 0                   # pass consecutivi nel giro di lancio
        self._order_counter = 0

        if first_attacker is None:
            self.attacker = self._first_attacker()
        else:
            self.attacker = first_attacker
        self.defender = self._next(self.attacker)

    # ------------------------------------------------------------- helpers

    def _next(self, p: int) -> int:
        """Giocatore successivo in senso orario (salta chi è uscito)."""
        nxt = (p + 1) % self.n_players
        while nxt in self.out and nxt != p:
            nxt = (nxt + 1) % self.n_players
        return nxt

    def _first_attacker(self) -> int:
        def key(p: int) -> tuple:
            trumps = [c for c in self.hands[p] if suit(c) == self.trump]
            if trumps:
                return (0, RANK_ORDER[rank(min(trumps, key=lambda c: RANK_ORDER[rank(c)]))])
            return (1, min(RANK_ORDER[rank(c)] for c in self.hands[p]))
        return min(range(self.n_players), key=key)

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
        """Carta che il difensore deve battere (prima coppia aperta)."""
        pair = self.open_pair()
        return pair["stack"][-1] if pair else None

    def table_ranks(self) -> set[str]:
        """Valori di TUTTE le carte sul tavolo (per il lancio/attacco)."""
        return {rank(c) for c in self.table_cards()}

    def can_transfer(self, player: int) -> bool:
        """Regole reali del переводной: il trasferimento è permesso solo se
        il difensore non ha ancora battuto NESSUNA carta dell'attacco, se il
        giocatore che riceverebbe l'attacco (il SUCCESSIVO in senso orario)
        ha carte in mano, se c'è spazio sul tavolo e — variante più diffusa —
        MAI nel primo giro."""
        if self.phase != "defend" or player != self.defender:
            return False
        if not self.hands[self._next(player)]:
            return False                       # niente transfer a mani vuote
        if len(self.table_cards()) >= MAX_PAIRS * 2 - 1:
            return False                       # tavolo pieno
        if self.first_round:
            return False                       # primo giro: vietato
        open_pairs = self.open_pairs()
        if not open_pairs:
            return False
        # tutte le carte aperte devono avere lo stesso valore (un solo
        # attacco "in corso") e NESSUNA carta dello stesso valore deve
        # essere già stata battuta — chi ha iniziato a difendere non può
        # più trasferire
        r = rank(open_pairs[0]["stack"][-1])
        if any(rank(p["stack"][-1]) != r for p in open_pairs):
            return False
        if any(rank(p["stack"][-1]) == r and not p["open"] for p in self.table):
            return False
        return True

    def transfer_ranks(self, player: int) -> list[str]:
        """Valori che `player` può usare per trasferire l'attacco corrente
        (l'ultima carta aperta). Vuoto se il trasferimento non è permesso."""
        if not self.can_transfer(player):
            return []
        r = rank(self.open_pairs()[-1]["stack"][-1])   # l'attacco corrente
        return [r] if any(rank(c) == r for c in self.hands[player]) else []

    def can_take(self, player: int) -> bool:
        return (self.phase == "defend" and player == self.defender
                and player not in self.out and bool(self.table))

    def can_pass(self, player: int) -> bool:
        if player in self.out:
            return False
        if self.phase == "throw_in":
            # passano a turno i lanciatori (mai il difensore)
            return player == self.thrower
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
        In throw_in può lanciare SOLO il lanciatore corrente (`thrower`)."""
        if self.phase not in ("attack", "throw_in"):
            raise ValueError("not the moment to attack")
        if player in self.out:
            raise ValueError("you are out of the game")
        if self.phase == "throw_in" and player != self.thrower:
            raise ValueError("not your turn to throw")
        if self.phase == "attack" and player != self.attacker:
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
        quando ci sono più attacchi aperti, es. apertura multi-carta o
        trasferimenti); se omesso, si batte la prima coppia aperta che la
        carta batte. Con più attacchi aperti la fase resta 'defend' finché
        non sono battuti tutti."""
        if self.phase != "defend" or player != self.defender:
            raise ValueError("not your turn to defend")
        if player in self.out:
            raise ValueError("you are out of the game")
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
            # tutto battuto: il giro dei lanci riparte dall'attaccante
            self.phase = "throw_in"
            self.thrower = self.attacker
            self.pass_count = 0

    def transfer(self, player: int, card: str) -> None:
        """Trasferimento (перевод): carta dello stesso valore dell'attacco
        corrente. La carta va ACCANTO all'attacco — diventa lei l'attacco
        aperto e, come nel gioco reale, il nuovo difensore dovrà battere
        TUTTE le carte del gruppo, una per una (ognuna è una coppia propria).
        L'attacco passa al giocatore SUCCESSIVO in senso orario (con 2
        giocatori torna all'attaccante, i ruoli si scambiano)."""
        if self.phase != "defend" or player != self.defender:
            raise ValueError("not your turn to defend")
        if card not in self.hands[player]:
            raise ValueError("card not in hand")
        if not self.can_transfer(player):
            raise ValueError("you cannot transfer now")
        if rank(card) not in self.transfer_ranks(player):
            raise ValueError("the card must match the attack rank")
        # l'attacco corrente è l'ULTIMA carta aperta (l'ultimo trasferimento)
        pair = self.open_pairs()[-1]
        idx = next(i for i, p in enumerate(self._sorted_table()) if p is pair)
        self._remove(player, card)
        self._add_pair(card, next_to=idx)     # nuova coppia accanto all'attacco
        self.last_action = "transfer"
        # chi ha trasferito è al sicuro e diventa l'attaccante del giro;
        # l'attacco passa al giocatore successivo
        self.attacker = player
        self.defender = self._next(player)

    def take(self, player: int) -> None:
        """Il difensore si arrende e prende tutte le carte del tavolo.
        Chi prende NON attacca: attacca il giocatore successivo al difensore
        (con 2 giocatori riattacca l'attaccante di prima)."""
        if not self.can_take(player):
            raise ValueError("you cannot take now")
        self.hands[player].extend(self.table_cards())
        self.table.clear()
        self._order_counter = 0
        self.last_action = "take"
        self.thrower = None
        self.pass_count = 0
        self._resolve_round()                    # prima: pescata e uscite
        if self.phase != "over":
            self.attacker = self._next(player)   # chi prende non attacca
            self.defender = self._next(self.attacker)

    def pass_turn(self, player: int) -> None:
        """In attack: chiude l'attacco multi-carta (tocca al difensore).
        In throw_in: il lanciatore corrente passa; quando tutti gli altri
        hanno passato, tavolo pulito e il difensore attacca il successivo."""
        if not self.can_pass(player):
            raise ValueError("you cannot pass now")
        if self.phase == "attack":
            self.last_action = "close_attack"
            self.phase = "defend"
            return
        # throw_in: il turno di lancio passa al successivo in senso orario
        # (saltando il difensore); il giro si chiude quando TUTTI gli altri
        # giocatori hanno passato consecutivamente
        self.pass_count += 1
        if self.pass_count >= self.n_players - 1:
            self.thrower = None
            self.pass_count = 0
        else:
            nxt = self._next(self.thrower)
            if nxt == self.defender:
                nxt = self._next(nxt)
            self.thrower = nxt
            self.last_action = "pass"
            return
        # tutti gli altri hanno passato: giro chiuso
        for pair in self.table:
            self.discard.extend(pair["stack"])
            if pair["defense"]:
                self.discard.append(pair["defense"])
        self.table.clear()
        self._order_counter = 0
        self.last_action = "clear"
        self.thrower = None
        self.pass_count = 0
        self._resolve_round()                    # prima: pescata e uscite
        if self.phase != "over":
            # chi si è difeso attacca il giro dopo (saltando gli usciti)
            self.attacker = self.defender if self.defender not in self.out \
                else self._next(self.defender)
            self.defender = self._next(self.attacker)

    # ------------------------------------------------------------- giro

    def _resolve_round(self) -> None:
        """Pescata fino a 6 e controllo vittoria (solo qui si vince).
        Si pesca in ordine di giro: dall'attaccante in senso orario fino
        al difensore (regola reale del durak). Gli usciti vengono marcati
        QUI (a mazzo finito); i ruoli del giro successivo li assegnano i
        chiamanti (take/pass_turn) DOPO questa chiamata."""
        self.first_round = False              # il primo giro è finito
        p = self.attacker
        for _ in range(self.n_players):
            while self.deck and len(self.hands[p]) < HAND_SIZE:
                self.hands[p].append(self.deck.pop(0))
            p = self._next(p)
        self.phase = "attack"
        if not self.deck:
            for p in range(self.n_players):
                if p not in self.out and not self.hands[p]:
                    self.out.append(p)
                    self.winner = p
            active = [p for p in range(self.n_players) if p not in self.out]
            if len(active) == 0:
                self.winner = -1               # pareggio totale (raro)
                self.phase = "over"
            elif len(active) == 1:
                # resta un solo giocatore con carte: è il durak
                self.phase = "over"

    # ------------------------------------------------------------- vista

    def public_state(self, viewer: int) -> dict:
        """Stato da inviare a `viewer`: le mani altrui sono nascoste
        (solo il conteggio in `hand_sizes`)."""
        my_hand = sorted(self.hands[viewer], key=lambda c: (RANK_ORDER[rank(c)], c))
        return {
            "trump": self.trump,
            "deck_count": len(self.deck),
            # la briscola è l'ultima carta del mazzo: resta visibile (faccia
            # in su) finché non viene pescata
            "trump_card": self.deck[-1] if self.deck else None,
            "hand": my_hand,
            "opp_count": len(self.hands[1 - viewer]) if self.n_players == 2 else 0,
            "hand_sizes": [len(h) for h in self.hands],
            "table": [dict(p) for p in self._sorted_table()],
            "attacker": self.attacker,
            "defender": self.defender,
            "thrower": self.thrower,
            "pass_count": self.pass_count,
            "n_players": self.n_players,
            "out": list(self.out),
            "viewer": viewer,
            "phase": self.phase,
            "can_take": self.can_take(viewer),
            "can_pass": self.can_pass(viewer),
            "transfer_ranks": self.transfer_ranks(viewer),
            "defender_empty": not self.hands[self.defender] if self.phase == "throw_in" else False,
            "winner": self.winner,
            "last_action": self.last_action,
        }
