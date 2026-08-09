# Durak Переводной — Telegram WebApp multigiocatore 1v1

Gioco di **Durak con la regola del trasferimento** (переводной дурак) come
WebApp di Telegram, ispirato al layout delle app di durak esistenti ma con
grafica moderna (feltro blu-notte, oro, carte flat in SVG).

- **Sotto**: la tua mano. **Sopra**: l'avversario con le carte coperte.
- **A sinistra**: il mazzo con il numero di carte rimaste (la briscola è il
  seme della carta in fondo; quando ne resta una sola viene scoperta).
- **Al centro**: le carte sul tavolo con animazioni (volano da mano a tavolo,
  la presa le riporta in mano, i giri puliti le fanno svanire nello scarto).
- **Regola переводной**: accanto all'attacco aperto c'è lo **slot tratteggiato
  con la freccia ⟳**. Se hai una carta dello stesso valore, lo slot si
  accende: cliccaci (o doppio-click sulla carta) per **trasferire l'attacco
  all'avversario** — i ruoli si scambiano e tocca a lui difendere.
- Timer 30s a mossa (anello attorno al chip di chi deve giocare; allo scadere
  mossa automatica), toast degli eventi, rivincita in-app.

## Regole implementate (1v1)

- Mazzo da 36 (6→A); 6 carte a testa; attacca chi ha la briscola più bassa.
- Difesa: battere (stesso seme più alto o briscola), **trasferire** con carta
  dello stesso valore (catene permesse), o prendere tutto.
- Dopo una difesa riuscita l'attaccante lancia solo carte dello stesso valore
  delle carte sul tavolo, max 6 coppie (12 carte); non si può attaccare un
  difensore senza carte.
- Presa → l'altro attacca; giro pulito → chi ha difeso attacca.
- Mazzo finito → vince chi resta senza carte; l'altro è il *durak*.

## Architettura

```
bot/main.py      bot Telegram (PTB v22): /durak = matchmaking + pulsante webapp
server/game.py   logica pura del gioco (nessuna dipendenza) — testata con pytest
server/ai.py     avversario automatico (demo + mosse di timeout)
server/room.py   stanze di gioco, WebSocket, timer, GC delle stanze
server/app.py    server aiohttp: pagina webapp + /ws + POST /api/match
webapp/          client HTML5 (SDK Telegram, SVG cards, animazioni FLIP)
tests/           pytest della logica (22 test)
scripts/smoke_test.py  partite multiplayer end-to-end via WebSocket
```

Flusso: `/durak` → il bot crea/unisce una stanza e invia il pulsante web_app
(URL `WEBAPP_URL/play?m=…&t=…&name=…`) → la webapp si collega via WebSocket →
partita in tempo reale. Il server tiene bot e gioco nello stesso processo.

## Avvio

```bash
# 1. ambiente
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt

# 2. token + URL (vedi .env.example)
export BOT_TOKEN=123456:ABC...
export WEBAPP_URL=https://tuo-tunnel.ngrok.io   # HTTPS obbligatorio per Telegram

# 3. avvio (senza BOT_TOKEN parte solo il server)
PORT=8765 .venv/Scripts/python.exe -m server.app
```

Sviluppo senza Telegram: `http://localhost:8765/play?demo=1` (avversario IA,
aggiungi `&seed=N` per riprodurre una mano specifica). In produzione il tunnel
deve puntare alla porta locale (`cloudflared tunnel --url http://localhost:8765`).

## Test

```bash
.venv/Scripts/python.exe -m pytest tests -q              # logica (22 test)
PORT=8765 .venv/Scripts/python.exe -m server.app &       # server di prova
SMOKE_BASE=http://localhost:8765 .venv/Scripts/python.exe scripts/smoke_test.py 4
```

## Deploy in produzione (Vercel + host persistente)

Il backend (WebSocket + bot) è un processo persistente con stato in memoria:
**non gira su Vercel** (serverless). Architettura consigliata e verificata:

```
Vercel (statico, gratis)          Host persistente (Render/Railway/Fly/VPS)
┌─────────────────────────┐      ┌──────────────────────────────────┐
│ webapp/ (index.html,    │  ws  │ python -m server.app             │
│ style.css, app.js, ...) │ ───► │  /ws  (WebSocket realtime)       │
│ vercel.json             │ api  │  /api/match  (matchmaking, CORS) │
└─────────────────────────┘      │  bot Telegram (polling)          │
                                 └──────────────────────────────────┘
```

1. **Webapp su Vercel**: `cd webapp && vercel --prod` (o dashboard con
   "Root Directory" = `webapp`). `vercel.json` mappa `/play` e `/static/*`.
   HTTPS gratuito — soddisfa il requisito dei pulsanti web_app di Telegram.
2. **Backend su un host persistente**: Render (blueprint pronto in
   `render.yaml`, piano free) o Docker (`Dockerfile`). Il server legge `PORT`
   dall'ambiente.
3. **Collegare i due**: in `webapp/config.js` imposta
   `window.DURAK_CONFIG = { wsUrl: "wss://durak-backend.onrender.com" }`
   (oppure il parametro `?ws=...` nell'URL, che ha precedenza). Il bot usa
   `WEBAPP_URL = https://...vercel.app` per il pulsante web_app.
4. **CORS**: il backend risponde a `/api/match` da qualunque origine di
   default (`CORS_ORIGINS=*`); restringere con l'elenco dei domini Vercel.

## Note di produzione

- I token nelle query (`m`, `t`) sono sufficienti per il matchmaking, ma prima
  di fidarsi dei dati inviati dalla webapp in produzione conviene validare
  `initData` con HMAC-SHA256 (segreto = HMAC-SHA256(bot_token, "WebAppData"));
  snippet di riferimento nel progetto "telegram bot giochi".
- Le stanze inattive vengono rimosse dopo 15 minuti; il bot riporta i giocatori
  alla loro stanza se riaprono il tavolo.
