# -*- coding: utf-8 -*-
"""Test del matchmaking (RoomManager):
- entro la finestra di grazia una stanza mai connessa è joinabile (flusso
  normale: il secondo giocatore arriva mentre il primo apre la webapp);
- dopo la finestra una stanza mai connessa NON blocca più la coda;
- il proprietario rientra sempre nella sua stanza con lo stesso token;
- appena il proprietario si connette, la stanza torna joinabile.
"""
import asyncio
import time

from server.room import ROOM_JOIN_GRACE, RoomManager


def test_matchmaking_grazia_e_sblocco():
    async def scenario():
        m = RoomManager()
        # u1 crea la stanza A ma non si connette mai
        ma, ta = m.register_human("u1", None, "Primo")
        # A invecchiata oltre la grazia → u2 NON viene catturato, stanza nuova B
        m.get(ma).created_at = time.monotonic() - ROOM_JOIN_GRACE - 5
        mb, _ = m.register_human("u2", None, "Secondo")
        assert mb != ma
        # u3 arriva subito dopo: entro la grazia si accoppia con u2
        mb3, _ = m.register_human("u3", None, "Terzo")
        assert mb3 == mb
        # il proprietario di A rientra sempre nella sua stanza, stesso token
        assert m.register_human("u1", None, "Primo") == (ma, ta)
        # appena il proprietario di A si connette, A torna joinabile
        m.get(ma).saw_connection = True
        m4, _ = m.register_human("u4", None, "Quarto")
        assert m4 == ma

    asyncio.run(scenario())


def test_rientro_nella_propria_stanza():
    async def scenario():
        m = RoomManager()
        mid1, tok1 = m.register_human("p1", None, "P1")
        mid1b, tok1b = m.register_human("p1", None, "P1")
        assert mid1b == mid1 and tok1b == tok1

    asyncio.run(scenario())
