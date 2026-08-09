/* config.js — configurazione del client, editabile a ogni deploy.
   wsUrl: indirizzo del server di gioco (WebSocket). Vuoto = stesso host
   (funziona in sviluppo e quando il backend serve la webapp).
   Su Vercel (webapp statica) va puntato al backend, es.:
   window.DURAK_CONFIG = { wsUrl: "wss://durak-backend.onrender.com" };
   Un parametro ?ws=... nell'URL ha la precedenza su questa impostazione.
*/
window.DURAK_CONFIG = { wsUrl: "" };
