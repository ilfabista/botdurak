/* config.js — configurazione del client, editabile a ogni deploy.
   wsUrl: indirizzo del server di gioco (WebSocket). Vuoto = stesso host
   (funziona in sviluppo e quando il backend serve la webapp).
   ORA: backend SEMPRE-ONLINE su Render (piano free, deploy da GitHub
   ilfabista/botdurak). Un parametro ?ws=... nell'URL ha la precedenza.
*/
window.DURAK_CONFIG = { wsUrl: "wss://durak-backend-4dzj.onrender.com" };
