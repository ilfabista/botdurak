/* config.js — configurazione del client, editabile a ogni deploy.
   wsUrl: indirizzo del server di gioco (WebSocket). Vuoto = stesso host
   (funziona in sviluppo e quando il backend serve la webapp).
   ORA: tunnel cloudflared verso il backend locale (URL TEMPORANEO — cambia
   a ogni riavvio del tunnel; quando il backend sarà su Render, mettere qui
   l'URL stabile, es. wss://durak-backend.onrender.com).
   Un parametro ?ws=... nell'URL ha la precedenza su questa impostazione.
*/
window.DURAK_CONFIG = { wsUrl: "wss://flowers-pocket-begin-front.trycloudflare.com" };
