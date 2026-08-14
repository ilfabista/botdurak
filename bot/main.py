# -*- coding: utf-8 -*-
"""Bot Telegram: porta d'ingresso al gioco e matchmaking.

Comandi:
- /start           → messaggio introduttivo + pulsante webapp (chat privata)
- /start durak     → deep link dal pulsante nei gruppi: matchmaking + webapp
- /durak           → matchmaking (chat privata)
- nei GRUPPI /durak NON apre la webapp (Telegram blocca i pulsanti web_app
  nei messaggi di gruppo): risponde con un bottone URL che porta in chat
  privata con /start durak già compilato.

Il gioco vero gira nella webapp: il bot costruisce l'URL con match_id e token
per il giocatore. L'import del modulo non deve richiedere il token (i test
importano senza). HTTPS obbligatorio per i pulsanti web_app (vedi README).
"""
from __future__ import annotations

import os
import pathlib
from urllib.parse import quote

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, Update,
                      WebAppInfo)
from telegram.ext import (Application, CallbackQueryHandler, ChatMemberHandler,
                          CommandHandler, ContextTypes)

GAME_TITLE = "🎴 Durak Переводной"
BUTTON_TEXT = "🃏 Apri il tavolo"


def _load_env() -> None:
    """Carica .env se presente (senza dipendenze; non sovrascrive le env già
    impostate). Utile per lo sviluppo locale."""
    env_file = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def game_keyboard(webapp_url: str, match_id: str, token: str, name: str) -> InlineKeyboardMarkup:
    url = f"{webapp_url}/play?m={match_id}&t={token}&name={quote(name)}"
    # ATTENZIONE: web_app vuole un WebAppInfo, NON una stringa — con una
    # stringa Telegram risponde BadRequest "field web_app must be of type
    # object" e l'handler muore in silenzio.
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(BUTTON_TEXT, web_app=WebAppInfo(url=url))
    ]])


def private_chat_keyboard(username: str) -> InlineKeyboardMarkup:
    """Bottone per i gruppi: URL verso la chat privata con /start durak."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎴 Apri il tavolo in chat privata",
                             url=f"https://t.me/{username}?start=durak")
    ]])


async def _bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    try:
        return (await context.bot.get_me()).username or ""
    except Exception:
        return ""


async def _durak_private(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         webapp_url: str, manager) -> None:
    """Matchmaking + pulsante webapp in chat privata."""
    user = update.effective_user
    if user is None:
        return
    name = user.first_name or "Giocatore"
    match_id, token = manager.register_human(user.id, update.effective_chat.id, name)
    room = manager.get(match_id)
    kb = game_keyboard(webapp_url, match_id, token, name)
    if room is not None and room.started:
        text = "Partita in corso: riprendi il tavolo."
    elif len(room.players) >= 2:
        text = "Avversario trovato! Apri il tavolo. 🎉"
    else:
        text = "Stanza creata: in attesa di un avversario…\nApri il tavolo e aspetta."
    await update.message.reply_text(text, reply_markup=kb)


def players_keyboard() -> InlineKeyboardMarkup:
    """Scelta del numero di giocatori (2-6)."""
    rows = [[InlineKeyboardButton(f"👥 {n}", callback_data=f"durak:{n}")
             for n in range(2, 7)]]
    return InlineKeyboardMarkup(rows)


async def _durak_multi(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       webapp_url: str, manager, players: int) -> None:
    """Stanza multi-giocatore: bottone del creatore + link da condividere."""
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None:
        return
    name = user.first_name or "Giocatore"
    match_id, token = manager.create_room(user.id, chat.id, name, players)
    kb = game_keyboard(webapp_url, match_id, token, name)
    invite = f"{webapp_url}/play?m={match_id}&join=1"
    room = manager.get(match_id)
    if room is not None and room.started:
        text = "Partita in corso: riprendi il tavolo."
    else:
        text = (
            f"🃏 Stanza da *{players} giocatori* creata!\n\n"
            "1️⃣ Apri il tavolo con il pulsante qui sotto\n"
            "2️⃣ Inoltra il link agli altri giocatori (si uniranno "
            "automaticamente quando apriranno il link)\n\n"
            f"📨 *Link da condividere:*\n`{invite}`\n\n"
            f"Posti occupati: {len(room.players)}/{players}"
        )
    await update.message.reply_text(text, reply_markup=kb)


def build_bot(token: str, webapp_url: str, manager) -> Application:
    """Costruisce l'Application PTB collegata al RoomManager condiviso."""
    if not webapp_url:
        raise RuntimeError("WEBAPP_URL mancante: serve l'URL https della webapp "
                           "(es. il dominio Vercel)")

    application = Application.builder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # deep link dai gruppi: /start durak → matchmaking diretto
        if context.args and context.args[0] == "durak":
            await _durak_private(update, context, webapp_url, manager)
            return
        await update.message.reply_text(
            f"{GAME_TITLE}\n\n"
            "Durak con la regola del *trasferimento* (переводной): se hai una "
            "carta dello stesso valore dell'attacco, puoi rigirarlo "
            "all'avversario. 🃏\n\n"
            "Invia /durak per trovare un avversario.",
        )

    async def durak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type != "private":
            # i pulsanti web_app NON funzionano nei messaggi di gruppo
            # (Telegram li rifiuta): bottone verso la chat privata
            username = await _bot_username(context)
            await update.message.reply_text(
                "🎴 Il tavolo si apre nella chat privata: qui i pulsanti del "
                "gioco non sono supportati. Premi il bottone qui sotto 👇",
                reply_markup=private_chat_keyboard(username),
            )
            return
        user = update.effective_user
        # stanza già attiva? si riprende il tavolo, senza ricreare
        if user is not None and user.id in manager.user_room:
            match_id, token = manager.user_room[user.id]
            room = manager.get(match_id)
            if room is not None and room.find_by_token(token) is not None:
                name = user.first_name or "Giocatore"
                kb = game_keyboard(webapp_url, match_id, token, name)
                if room.started:
                    text = "Partita in corso: riprendi il tavolo."
                elif len(room.players) < room.max_players:
                    text = (f"La tua stanza da {room.max_players} giocatori "
                            "è ancora aperta: condividi il link per far "
                            "entrare gli altri, poi apri il tavolo.")
                else:
                    text = "Stanza piena! Apri il tavolo. 🎉"
                await update.message.reply_text(text, reply_markup=kb)
                return
        await update.message.reply_text(
            "🎴 *Durak Переводной* — con quanti giocatori vuoi giocare?",
            reply_markup=players_keyboard(),
        )

    async def durak_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.callback_query.answer()
        await durak(update, context)

    async def durak_multi_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Callback durak:N — crea la stanza multi-giocatore."""
        query = update.callback_query
        await query.answer()
        try:
            players = int(query.data.split(":")[1])
        except (IndexError, ValueError):
            players = 2
        players = max(2, min(6, players))
        await _durak_multi(update, context, webapp_url, manager, players)

    async def on_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Bot aggiunto a un gruppo: messaggio di benvenuto col bottone."""
        new = update.my_chat_member.new_chat_member
        if new.status not in ("member", "administrator"):
            return
        if update.effective_chat.type == "private":
            return
        username = await _bot_username(context)
        await update.effective_chat.send_message(
            f"Ciao! {GAME_TITLE} si gioca nella chat privata del bot.\n"
            "Premi il bottone qui sotto per aprire il tavolo 👇",
            reply_markup=private_chat_keyboard(username),
        )

    async def notify_start(chat_ids: list[int]) -> None:
        """Inviato dal RoomManager quando entrambi i giocatori sono connessi."""
        for chat_id in chat_ids:
            try:
                await application.bot.send_message(
                    chat_id, "🎉 Partita iniziata! Buona fortuna 🍀")
            except Exception:
                pass

    manager.on_start = notify_start
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("durak", durak))
    application.add_handler(CallbackQueryHandler(durak_cb, pattern="^durak$"))
    application.add_handler(CallbackQueryHandler(durak_multi_cb, pattern=r"^durak:[2-6]$"))
    application.add_handler(ChatMemberHandler(on_added_to_group,
                                              ChatMemberHandler.MY_CHAT_MEMBER))
    return application


if __name__ == "__main__":
    # Avvio standalone (solo bot, senza server web) — utile per debug.
    from server.room import RoomManager
    import asyncio

    async def run() -> None:
        _load_env()
        token = os.environ["BOT_TOKEN"]
        url = os.environ["WEBAPP_URL"]
        manager = RoomManager()
        app = build_bot(token, url, manager)
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()

    asyncio.run(run())
