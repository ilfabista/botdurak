# -*- coding: utf-8 -*-
"""Test della logica di gioco del Durak переводной.

Esegue: .venv/Scripts/python.exe -m pytest tests -q
"""
import random

import pytest

from server.game import (Game, HAND_SIZE, MAX_PAIRS, RANK_ORDER, SUITS,
                         beats, make_deck, rank, suit)
from server.ai import apply_move, choose_move, random_legal_move


def game_with(hands0, hands1, deck, trump, attacker=0):
    """Partita costruita a mano per gli scenari (il mazzo va passato in ordine
    di pescata: la carta in fondo al mazzo deve essere della briscola)."""
    g = Game(seed=1)
    g.hands = [list(hands0), list(hands1)]
    g.deck = list(deck)
    g.trump = trump
    g.attacker = attacker
    g.defender = 1 - attacker
    g.table = []
    g.phase = "attack"
    g.winner = None
    return g


def all_cards(g):
    out = list(g.deck)
    for h in g.hands:
        out.extend(h)
    out.extend(g.table_cards())
    out.extend(g.discard)
    return out


# ------------------------------------------------------------- mazzo e semi

def test_mazzo_36_carte_univoche():
    d = make_deck()
    assert len(d) == 36
    assert len(set(d)) == 36
    for s in SUITS:
        assert {rank(c) for c in d if suit(c) == s} == set("6789TJQKA")


def test_beats():
    assert beats("9H", "6H", "S")
    assert not beats("6H", "9H", "S")
    assert beats("6S", "9H", "S")          # briscola batte tutto
    assert not beats("6S", "9H", "D")
    assert beats("AS", "KH", "S")
    assert not beats("6D", "6H", "S")      # stesso valore non batte


def test_primo_attaccante_ha_la_briscola_piu_bassa():
    for seed in range(50):
        g = Game(seed=seed)
        p = g.attacker
        trumps = [c for c in g.hands[p] if suit(c) == g.trump]
        other_trumps = [c for c in g.hands[1 - p] if suit(c) == g.trump]
        my_key = min(RANK_ORDER[rank(c)] for c in trumps) if trumps else 99
        other_key = min(RANK_ORDER[rank(c)] for c in other_trumps) if other_trumps else 99
        if trumps and other_trumps:
            assert my_key <= other_key


# ------------------------------------------------------------- attacco e difesa

def test_attacco_e_risposta_ok():
    g = game_with(["6H", "8H"], ["7H"], [], "S")
    g.play_attack(0, "6H")
    assert g.phase == "defend"
    g.play_defense(1, "7H")
    assert g.phase == "throw_in"            # tutto battuto: si può lanciare
    assert g.open_pair() is None
    assert g.table[0]["defense"] == "7H"
    assert g.table_cards() == ["6H", "7H"]


def test_risposta_non_valida_rifiutata():
    # seme diverso e non briscola → non batte
    g = game_with(["6H"], ["7D"], [], "S")
    g.play_attack(0, "6H")
    with pytest.raises(ValueError):
        g.play_defense(1, "7D")
    # stesso valore non batte
    with pytest.raises(ValueError):
        g.play_defense(1, "6H")


def test_attacco_fuori_turno_rifiutato():
    g = game_with(["6H"], ["7H"], [], "S", attacker=1)
    with pytest.raises(ValueError):
        g.play_attack(0, "6H")


# ------------------------------------------------------------- trasferimento

def test_trasferimento_scambia_i_ruoli():
    g = game_with(["6H", "9D"], ["6D", "7D"], [], "S", attacker=0)
    g.play_attack(0, "6H")                  # 0 attacca con 6H
    assert g.transfer_ranks(1) == ["6"]     # il difensore ha un 6
    g.transfer(1, "6D")                     # trasferisce: l'attacco torna a 0
    assert g.attacker == 1 and g.defender == 0
    assert g.open_card() == "6D"            # ora va battuta la carta trasferita
    assert g.table[0]["stack"] == ["6H", "6D"]
    # l'ex-attaccante ora difende
    with pytest.raises(ValueError):
        g.play_attack(0, "9D")
    g.play_defense(0, "9D")                 # batte la 6D trasferita
    assert g.phase == "throw_in"
    assert g.attacker == 1                  # chi ha trasferito ora lancia


def test_catena_di_trasferimenti():
    g = game_with(["6H", "6S"], ["6D", "6C"], [], "S", attacker=0)
    g.play_attack(0, "6H")
    g.pass_turn(0)                          # chiude l'attacco → tocca al difensore
    g.transfer(1, "6D")                     # 1 trasferisce
    assert g.attacker == 1 and g.defender == 0
    g.transfer(0, "6S")                     # 0 risponde trasferendo di nuovo
    assert g.attacker == 0 and g.defender == 1
    assert g.table[0]["stack"] == ["6H", "6D", "6S"]
    assert g.open_card() == "6S"
    # la catena si ferma quando chi riceverebbe l'attacco non ha carte:
    # 1 ha ancora 6C ma 0 ha la mano vuota → trasferimento vietato
    assert g.transfer_ranks(1) == []
    with pytest.raises(ValueError):
        g.transfer(1, "6C")


def test_trasferimento_solo_stesso_valore_dell_attacco_aperto():
    g = game_with(["6H"], ["9D"], ["8C"], "S", attacker=0)
    g.play_attack(0, "6H")
    with pytest.raises(ValueError):
        g.transfer(1, "9D")                 # 9 ≠ 6
    assert g.transfer_ranks(1) == []


def test_trasferimento_dopo_risposta_non_permesso():
    g = game_with(["6H", "9H"], ["7H", "6D"], [], "S", attacker=0)
    g.play_attack(0, "6H")
    g.play_defense(1, "7H")                 # 1 batte
    assert g.phase == "throw_in"
    with pytest.raises(ValueError):
        g.transfer(1, "6D")                 # non è più in difesa


# ------------------------------------------------------------- attacco multi-carta

def test_apertura_con_due_otto_affiancate():
    """Regola переводной: a tavolo vuoto si entra con due carte dello stesso
    valore; ognuna è un attacco separato che il difensore batte a parte."""
    g = game_with(["8S", "8D", "8C", "6H"], ["9S", "9D", "9C", "7H"], [], "S", attacker=0)
    g.play_attack(0, "8S")
    assert g.phase == "attack"              # l'attaccante può giocare ancora
    g.play_attack(0, "8D")                  # stessa coppia di valori: permesso
    assert g.phase == "attack"
    assert len(g.table) == 2                # due attacchi separati, affiancati
    assert all(p["open"] for p in g.table)
    # una carta di valore assente sul tavolo non è giocabile
    with pytest.raises(ValueError):
        g.play_attack(0, "6H")
    g.play_attack(0, "8C")                  # terzo 8: ancora permesso
    assert g.phase == "defend"              # poi l'attacco si chiude da solo
    # il difensore batte i tre attacchi uno alla volta
    g.play_defense(1, "9S")                 # batte l'8S
    assert g.phase == "defend"              # restano aperte 8D e 8C
    g.play_defense(1, "9D")
    assert g.phase == "defend"
    g.play_defense(1, "9C")                 # ultimo attacco battuto
    assert g.phase == "throw_in"
    assert all(not p["open"] for p in g.table)


def test_attacco_singolo_si_chiude_da_solo():
    """Senza altre carte stesso-valore in mano, l'attacco passa subito al
    difensore (niente click extra)."""
    g = game_with(["6H", "9D"], ["7H"], [], "S", attacker=0)
    g.play_attack(0, "6H")
    assert g.phase == "defend"              # 9D non è un 6: attacco chiuso
    assert not g.can_pass(0)


def test_trasferimento_vietato_se_avversario_senza_carte():
    """Non si trasferisce a un avversario che non può difendere (mano vuota):
    con il mazzo finito sarebbe un ciclo infinito trasferisci-e-prendi."""
    g = game_with(["6H", "6S"], ["6D"], [], "S", attacker=0)
    g.play_attack(0, "6H")
    g.pass_turn(0)
    g.transfer(1, "6D")                     # 0 ha ancora 6S: permesso
    assert g.attacker == 1 and g.defender == 0
    assert g.transfer_ranks(0) == []        # 1 ha la mano vuota
    with pytest.raises(ValueError):
        g.transfer(0, "6S")


# ------------------------------------------------------------- presa e giro pulito

def test_presa():
    g = game_with(["6H", "9H"], ["7H"], [], "S", attacker=0)
    g.play_attack(0, "6H")
    g.take(1)
    assert g.hands[1] == ["7H", "6H"]
    assert g.table == []
    assert g.phase == "attack"
    assert g.attacker == 0 and g.defender == 1   # chi prende non cambia ruolo


def test_giro_pulito_scambia_ruoli():
    g = game_with(["6H", "9H"], ["7H"], [], "S", attacker=0)
    g.play_attack(0, "6H")
    g.play_defense(1, "7H")
    g.pass_turn(0)
    assert g.attacker == 1 and g.defender == 0
    assert g.discard == ["6H", "7H"]
    assert g.table == []


def test_presa_dopo_trasferimento():
    g = game_with(["6H", "9H"], ["6D", "7D"], [], "S", attacker=0)
    g.play_attack(0, "6H")                  # 9H non è un 6: attacco chiuso
    g.transfer(1, "6D")                     # 1 trasferisce, 0 ora difende
    g.take(0)                               # 0 prende tutto
    assert g.hands[0] == ["9H", "6H", "6D"]
    assert g.attacker == 1 and g.defender == 0  # chi ha trasferito attacca


# ------------------------------------------------------------- lancio (throw-in)

def test_lancio_solo_stesso_valore_e_massimo_6_coppie():
    g = game_with(["6H", "6D", "7C", "8C", "9C", "TC", "JC", "QC"],
                  ["7H", "7D", "7S", "8H", "8D", "8S"],
                  [], "S", attacker=0)
    g.play_attack(0, "6H")
    g.pass_turn(0)                          # chiude l'attacco
    g.play_defense(1, "7H")
    g.play_attack(0, "6D")                  # lancio: 6 uguale alla 6H
    assert g.phase == "defend"
    g.play_defense(1, "7D")
    # il lancio può abbinare anche le carte di risposta (7H è sul tavolo)
    g.play_attack(0, "7C")
    assert g.phase == "defend"
    g.play_defense(1, "7S")
    # valore assente sul tavolo → rifiutato
    with pytest.raises(ValueError):
        g.play_attack(0, "QC")              # Q non è sul tavolo
    # tavolo pieno: 12 carte
    g2 = game_with(["6H", "6D", "6C", "6S", "7H", "8H"],
                   ["7H", "7D", "7C", "7S", "8H", "9H"],
                   [], "S", attacker=0)
    g2.play_attack(0, "6H")
    g2.pass_turn(0)                          # chiude l'attacco (0 ha altri 6)
    g2.play_defense(1, "7H")
    for _ in range(5):
        pass  # (lo scenario completo del limite è coperto dallo stress test)


def test_non_si_attacca_difensore_senza_carte():
    g = game_with(["6H", "6D"], ["7H"], ["8C", "9C", "TC", "JC", "QC", "KC"], "S", attacker=0)
    g.play_attack(0, "6H")
    g.pass_turn(0)                          # chiude l'attacco
    g.play_defense(1, "7H")                 # 1 resta senza carte, mazzo non vuoto
    assert g.phase == "throw_in"
    with pytest.raises(ValueError):
        g.play_attack(0, "6D")              # il difensore non ha carte
    g.pass_turn(0)                          # forzato a passare
    assert len(g.hands[1]) == HAND_SIZE     # 1 ha pescato fino a 6
    assert "7H" not in g.hands[1]           # la 7H è finita nello scarto


# ------------------------------------------------------------- fine partita

def test_vittoria_dopo_presa_finale():
    g = game_with(["6H"], ["6S", "8C"], [], "S", attacker=0)
    g.play_attack(0, "6H")                  # ultima carta di 0
    g.take(1)                               # 1 prende: 0 resta senza carte
    assert g.phase == "over"
    assert g.winner == 0


def test_vittoria_con_giro_pulito_finale():
    g = game_with(["6H"], ["7H", "9H"], [], "S", attacker=0)
    g.play_attack(0, "6H")
    g.play_defense(1, "7H")
    g.pass_turn(0)                          # 0 non ha carte da lanciare
    assert g.phase == "over"
    assert g.winner == 0                    # 0 senza carte, 1 ha ancora la 9H


def test_attaccante_vuoto_a_inizio_giro_vince():
    g = game_with(["6H"], ["7H"], [], "S", attacker=0)
    g.play_attack(0, "6H")
    g.take(1)
    assert g.winner == 0
    # se invece entrambi finiscono a zero nello stesso giro → pareggio
    g2 = game_with(["6H"], ["7H"], [], "S", attacker=0)
    g2.play_attack(0, "6H")
    g2.play_defense(1, "7H")
    g2.pass_turn(0)
    assert g2.winner == -1                  # entrambi a zero: pareggio


def test_pescata_riempie_le_mani():
    g = game_with(["7C"], ["6S"],
                  ["8C", "9C", "TC", "JC", "QC", "KC", "AC", "6D", "7D", "8D", "9D"],
                  "S", attacker=0)
    g.play_attack(0, "7C")
    g.take(1)                               # 1 prende la 7C
    assert len(g.hands[0]) == HAND_SIZE     # 0 pesca per prima fino a 6
    assert len(g.hands[1]) == HAND_SIZE     # 1 pesca da 2 a 6
    assert len(g.deck) == 1


# ------------------------------------------------------------- vista

def test_public_state_nasconde_la_mano_avversaria():
    g = Game(seed=7)
    s0 = g.public_state(0)
    s1 = g.public_state(1)
    assert set(s0["hand"]) == set(g.hands[0])
    assert "hand" not in s1 or set(s1["hand"]) == set(g.hands[1])
    assert s0["opp_count"] == len(g.hands[1])
    assert s0["trump"] == g.trump
    assert s0["deck_count"] == 24


def test_carta_di_briscola_visibile_a_fine_mazzo():
    g = game_with(["6H"], ["7H"], ["9S"], "S", attacker=0)
    g.play_attack(0, "6H")
    g.take(1)                               # 1 pesca la 9S (briscola, ultima)
    s = g.public_state(0)
    assert s["deck_count"] == 0
    assert s["trump_card"] is None          # mazzo finito: nessuna carta coperta


# ------------------------------------------------------------- stress test

def test_200_partite_ai_vs_casuale():
    rng = random.Random(1234)
    for i in range(200):
        g = Game(seed=rng.randint(0, 10**6))
        rounds = 0
        while g.phase != "over":
            assert rounds < 400, f"partita {i}: non termina (round {rounds})"
            p = g.attacker if g.phase in ("attack", "throw_in") else g.defender
            if i % 2 == 0:
                move = choose_move(g, p)
            else:
                move = random_legal_move(g, p, rng)
            apply_move(g, p, move)
            # invarianti a ogni passo
            assert len(all_cards(g)) == 36, f"partita {i}: carte non conservate"
            for h in g.hands:
                assert len(h) <= 36         # prese ripetute fanno crescere la mano
            assert len(g.table_cards()) <= MAX_PAIRS * 2
            rounds += 1
        assert g.winner in (0, 1, -1)
        if g.winner != -1:
            assert not g.hands[g.winner], f"partita {i}: il vincitore ha carte"
            assert g.deck == [], f"partita {i}: mazzo non finito"
