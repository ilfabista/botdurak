/* app.js — client webapp del Durak Переводной.
   - WebSocket realtime con il server (/ws)
   - Rendering di stato con animazioni FLIP (le carte volano da mano→tavolo,
     tavolo→mano, mazzo→mano; scarti svaniscono verso l'angolo)
   - Regola переводной: slot tratteggiato ⟳ accanto all'attacco aperto
   - Timer ad anello attorno al chip di chi deve muovere
   - Lobby e schermata di fine partita con rivincita
*/
(() => {
'use strict';

const $ = s => document.querySelector(s);
const rankOf = c => c[0];
const suitOf = c => c[1];
const RANK_ORDER = { 6: 0, 7: 1, 8: 2, 9: 3, T: 4, J: 5, Q: 6, K: 7, A: 8 };
const SUIT_SYM = { H: '♥', D: '♦', C: '♣', S: '♠' };
const SUIT_NAME = { H: 'Hearts', D: 'Diamonds', C: 'Clubs', S: 'Spades' };

const state = {
  s: null,          // ultimo stato dal server
  prev: null,       // snapshot precedente {hand, table, opp, deck}
  prevS: null,      // stato precedente completo (per i toast)
  first: true,      // primo stato ricevuto
  started: false,
  selected: null,   // carta selezionata in difesa
  rects: {},        // rect pre-render
  conn: null,
};

/* larghezza reale della carta (la CSS var --card-w è un clamp()) */
let _cardW = null;
function cardW() {
  if (_cardW) return _cardW;
  const d = document.createElement('div');
  d.style.cssText = 'position:fixed;left:-9999px;top:0;width:var(--card-w);height:1px;';
  document.body.appendChild(d);
  _cardW = d.offsetWidth;
  d.remove();
  return _cardW;
}
/* affiancamento tra carte dello stesso valore (regola переводной) */
const STACK_OFF = 38;

function beatsCard(a, b, trump) {
  if (suitOf(a) === suitOf(b)) return RANK_ORDER[rankOf(a)] > RANK_ORDER[rankOf(b)];
  return suitOf(a) === trump;
}
function tableCards(s) {
  const out = [];
  for (const p of s.table) { out.push(...p.stack); if (p.defense) out.push(p.defense); }
  return out;
}
function tableRanks(s) {
  const r = new Set();
  for (const c of tableCards(s)) r.add(rankOf(c));
  return r;
}
function isMyTurn(s) {
  if (!s || s.phase === 'over') return false;
  if (s.phase === 'attack' || s.phase === 'throw_in') return s.attacker === s.viewer;
  return s.defender === s.viewer;
}

/* ============================== WebSocket ============================== */

function wsUrl() {
  // precedenza: parametro ?ws=... > config.js > stesso host
  const q = new URLSearchParams(location.search).get('ws');
  let base = q || (window.DURAK_CONFIG && window.DURAK_CONFIG.wsUrl) || '';
  if (!base) return (location.protocol === 'https:' ? 'wss' : 'ws') + '://' + location.host;
  if (!/^[a-z]+:\/\//i.test(base)) {
    base = (location.protocol === 'https:' ? 'wss' : 'ws') + '://' + base;
  }
  return base.replace(/\/+$/, '');
}

function connect() {
  const p = new URLSearchParams(location.search);
  if (!p.get('t')) {
    let t = localStorage.getItem('durak_demo_t');
    if (!t) { t = crypto.randomUUID(); localStorage.setItem('durak_demo_t', t); }
    p.set('t', t);
  }
  history.replaceState(null, '', location.pathname + '?' + p.toString());
  state.conn = new WebSocket(`${wsUrl()}/ws?${p.toString()}`);
  state.conn.onmessage = ev => {
    let m;
    try { m = JSON.parse(ev.data); } catch { return; }
    if (m.type === 'state') applyState(m.state);
    else if (m.type === 'toast') toast(m.text);
    else if (m.type === 'error') toast(m.text, true);
  };
  state.conn.onclose = () => {
    if (!state.s || state.s.phase !== 'over') toast('Connection lost: reconnecting…', true);
    setTimeout(connect, 2200);
  };
}

function send(obj) {
  if (state.conn && state.conn.readyState === 1) state.conn.send(JSON.stringify(obj));
}

/* ============================== stato e animazioni ============================== */

function captureRects() {
  state.rects = {};
  document.querySelectorAll('[data-id]').forEach(el => {
    state.rects[el.dataset.id] = el.getBoundingClientRect();
  });
  const opp = $('#opp-hand'); if (opp) state.rects['opp-area'] = opp.getBoundingClientRect();
  const deck = $('#deck-stack'); if (deck) state.rects['deck-area'] = deck.getBoundingClientRect();
  const lane = $('#lane'); if (lane) state.rects['discard-area'] = lane.getBoundingClientRect();
}

function applyState(s) {
  const deal = !state.started && s.started;
  captureRects();
  state.prevS = state.s;
  state.s = s;
  state.started = s.started;
  renderAll(s);
  if (deal) { dealIn(); }
  else { animateTransitions(s); }
  state.prev = { hand: new Set(s.hand), table: new Set(tableCards(s)), opp: s.opp_count, deck: s.deck_count };
  if (state.first) { state.first = false; toast('🎴 Game started — trump ' + SUIT_SYM[s.trump]); }
  eventToasts(s);
}

/* animazione di consegna iniziale: dal mazzo alle mani */
function dealIn() {
  const src = state.rects['deck-area'];
  const cards = [...document.querySelectorAll('#hand .hcard')];
  cards.forEach((w, i) => { if (src) flyTo(w, src, { delay: 80 + i * 55 }); });
  const backs = [...document.querySelectorAll('#opp-hand .opp-card')];
  backs.forEach((b, i) => { if (src) flyTo(b, src, { delay: 160 + i * 55 }); });
}

/* diff tra stato precedente e nuovo: voli e sparizioni */
function animateTransitions(s) {
  const prev = state.prev;
  if (!prev) return;
  const tab = new Set(tableCards(s));

  // carte nuove sul tavolo: dalla mia mano (rect per carta) o dall'area avversaria
  for (const c of tab) {
    if (prev.table.has(c)) continue;
    const elc = cardNode(c);
    if (!elc) continue;
    const src = state.rects['c-' + c] || state.rects['opp-area'];
    if (src) flyTo(elc, src, { dur: 500 });
  }

  // carte in mano che erano sul tavolo: presa → volano alla mano
  for (const c of s.hand) {
    if (!prev.table.has(c)) continue;
    const elc = cardNode(c);
    const src = state.rects['c-' + c];
    if (elc && src) flyTo(elc, src, { dur: 480 });
  }

  // carte nuove in mano: pescate dal mazzo UNA PER UNA (cascata con ritardo
  // crescente: si vede ogni carta lasciare il mazzo e raggiungere la mano)
  const drawn = s.hand.filter(c => !prev.hand.has(c) && !prev.table.has(c));
  drawn.forEach((c, i) => {
    const elc = cardNode(c);
    if (elc && state.rects['deck-area']) flyTo(elc, state.rects['deck-area'], { delay: 140 + i * 110 });
  });

  // carte sparite dal tavolo: fine giro (clear → si girano e scivolano nella
  // lane a destra, il passaggio di turno visibile) o presa dell'avversario
  // (take → volano da lui). Deciso dal last_action: dopo un clear la pescata
  // fa crescere opp_count e l'euristica sul conteggio sbaglierebbe.
  if (s.last_action === 'clear') {
    for (const c of prev.table) {
      if (tab.has(c) || s.hand.includes(c)) continue;
      ghostFly(c, state.rects['discard-area'], s, { flip: true });
    }
  } else if (s.last_action === 'take' && s.opp_count > prev.opp) {
    for (const c of prev.table) {
      if (tab.has(c) || s.hand.includes(c)) continue;
      ghostFly(c, state.rects['opp-area'], s);
    }
  }
}

/* elemento animabile di una carta: wrapper in mano, card sul tavolo */
function cardNode(c) {
  const inHand = document.querySelector(`#hand [data-id="wrap-${c}"]`);
  if (inHand) return inHand;
  return document.querySelector(`[data-id="c-${c}"]`);
}

function flyTo(el, src, opts = {}) {
  const dst = el.getBoundingClientRect();
  if (!src || (Math.abs(src.x - dst.x) < 8 && Math.abs(src.y - dst.y) < 8)) return;
  // salva gli inline originali: al termine vanno RIPRISTINATI (non svuotati),
  // altrimenti si perdono posizionamenti come l'affiancamento delle carte
  const origLeft = el.style.left, origTop = el.style.top, origMargin = el.style.margin;
  el.style.position = 'fixed';
  el.style.left = '0';
  el.style.top = '0';
  el.style.margin = '0';
  el.style.zIndex = '90';
  const dx = src.x - dst.x;
  const dy = src.y - dst.y;
  const sc = Math.min(src.w / Math.max(dst.w, 1), 1.6);
  el.style.transform = `translate(${dx}px, ${dy}px) scale(${sc})`;
  void el.offsetWidth; /* forza il layout */
  const anim = el.animate(
    [{ transform: el.style.transform, opacity: 1 }, { transform: 'none', opacity: 1 }],
    { duration: opts.dur || 460, delay: opts.delay || 0, easing: 'cubic-bezier(.25,1.25,.35,1)' }
  );
  anim.onfinish = () => {
    el.style.position = '';
    el.style.left = origLeft;
    el.style.top = origTop;
    el.style.margin = origMargin;
    el.style.transform = '';
    el.style.zIndex = '';
  };
}

/* carta che lascia il tavolo senza destinazione visibile: clone che svanisce
   (presa avversaria) o che si GIRA e scivola nella lane a destra (fine giro) */
function ghostFly(card, target, s, opts = {}) {
  const src = state.rects['c-' + card];
  if (!src) return;
  const ghost = document.createElement('div');
  ghost.className = 'card ghost';
  ghost.innerHTML = Cards.face(card, suitOf(card) === s.trump);
  ghost.style.left = src.x + 'px';
  ghost.style.top = src.y + 'px';
  ghost.style.width = src.w + 'px';
  ghost.style.height = src.h + 'px';
  document.body.appendChild(ghost);
  const g = ghost.getBoundingClientRect();
  const t = target || { x: innerWidth / 2, y: 40, w: 60, h: 84 };
  const dx = t.x - g.x + (t.w - g.w) / 2;
  const dy = t.y - g.y + (t.h - g.h) / 2;
  if (opts.flip) {
    // fine giro: la carta si gira (faccia in giù a metà volo) e scivola a
    // destra nella lane, dimensione reale (mai ingrandita)
    const dur = 760;
    const anim = ghost.animate([
      { transform: 'none', opacity: 1 },
      { transform: `translate(${dx}px, ${dy}px) rotateY(90deg)`, offset: 0.45 },
      { transform: `translate(${dx}px, ${dy}px) rotateY(90deg)`, offset: 0.55 },
      { transform: `translate(${dx}px, ${dy}px) rotateY(0deg)`, opacity: 0.85 },
    ], { duration: dur, easing: 'cubic-bezier(.3,.65,.3,1)' });
    setTimeout(() => { ghost.innerHTML = Cards.back(); }, dur * 0.5);
    anim.onfinish = () => {
      ghost.remove();
      // la lane accumula un dorso per ogni carta battuta (lo scarto)
      const mini = document.createElement('div');
      mini.className = 'lane-mini';
      mini.dataset.id = 'c-' + card;
      mini.innerHTML = `<div class="card">${Cards.back()}</div>`;
      $('#lane').appendChild(mini);
    };
    return;
  }
  ghost.animate(
    [
      { transform: 'none', opacity: 1 },
      { transform: `translate(${dx}px, ${dy}px) scale(.9)`, opacity: 0.12 },
    ],
    { duration: 430, easing: 'cubic-bezier(.3,.8,.3,1)' }
  ).onfinish = () => ghost.remove();
}

/* ============================== rendering ============================== */

function avatarHtml(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.codePointAt(0)) % 360;
  const initials = name.trim().split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase() || '?';
  return { initials, bg: `linear-gradient(135deg, hsl(${h} 45% 42%), hsl(${(h + 40) % 360} 50% 30%))` };
}

function renderAll(s) {
  renderChips(s);
  renderDeck(s);
  renderOppHand(s);
  renderPairs(s);
  renderHand(s);
  renderActions(s);
  renderOverlay(s);
}

function renderChips(s) {
  const me = avatarHtml(s.my_name);
  const opp = avatarHtml(s.opp_name);
  const ma = $('#me-avatar'); ma.textContent = me.initials; ma.style.background = me.bg;
  const oa = $('#opp-avatar'); oa.textContent = opp.initials; oa.style.background = opp.bg;
  $('#me-name').textContent = s.my_name;
  $('#opp-name').textContent = s.opp_name;
  const mb = $('#me-badge'), ob = $('#opp-badge');
  if (mb.textContent !== String(s.hand.length)) { mb.textContent = s.hand.length; mb.classList.remove('pop'); void mb.offsetWidth; mb.classList.add('pop'); }
  if (ob.textContent !== String(s.opp_count)) { ob.textContent = s.opp_count; ob.classList.remove('pop'); void ob.offsetWidth; ob.classList.add('pop'); }
  $('#trump-chip').innerHTML = `${SUIT_SYM[s.trump]}&nbsp;<b>Trump</b>`;
  $('#trump-chip').title = `Trump: ${SUIT_NAME[s.trump]}`;
}

function renderDeck(s) {
  const c = $('#deck-count');
  if (c.textContent !== String(s.deck_count)) {
    c.textContent = s.deck_count;
    c.classList.remove('pop'); void c.offsetWidth; c.classList.add('pop');
  }
  const reveal = $('#trump-reveal');
  if (s.trump_card) {
    reveal.innerHTML = `<div class="card">${Cards.face(s.trump_card, true)}</div>`;
    reveal.title = 'Last card of the deck (trump)';
  } else {
    reveal.innerHTML = '';
  }
  // i dorsi del mazzetto
  document.querySelectorAll('#deck-stack .mini .card').forEach(el => {
    if (!el.querySelector('svg')) el.innerHTML = Cards.back();
  });
}

function renderOppHand(s) {
  const box = $('#opp-hand');
  const n = s.opp_count;
  if (box.children.length !== n) {
    box.innerHTML = '';
    for (let i = 0; i < n; i++) {
      const w = document.createElement('div');
      w.className = 'opp-card';
      w.innerHTML = `<div class="card">${Cards.back()}</div>`;
      box.appendChild(w);
    }
  }
}

function renderPairs(s) {
  const box = $('#pairs');
  box.innerHTML = '';
  s.table.forEach((p, i) => {
    const pair = document.createElement('div');
    pair.className = 'pair' + (p.open ? ' open' : '');
    pair.dataset.idx = i;   // indice della coppia: target esplicito per il beat
    // carte dello stesso valore AFFIANCATE (mai una sopra l'altra): la fila
    // cresce verso destra; la risposta si posa sopra l'ultima carta.
    // Le coppie completate RESTANO al centro finché il giro non si chiude.
    const n = p.stack.length;
    pair.style.width = (cardW() + (n - 1) * STACK_OFF + (p.defense ? 26 : 0)) + 'px';
    p.stack.forEach((card, si) => {
      const pc = document.createElement('div');
      pc.className = 'pc';
      pc.dataset.id = 'c-' + card;
      pc.style.left = (si * STACK_OFF) + 'px';
      pc.innerHTML = Cards.face(card, suitOf(card) === s.trump);
      pair.appendChild(pc);
    });
    if (p.defense) {
      const pc = document.createElement('div');
      pc.className = 'pc def';
      pc.dataset.id = 'c-' + p.defense;
      pc.style.left = ((n - 1) * STACK_OFF + 8) + 'px';
      pc.innerHTML = Cards.face(p.defense, suitOf(p.defense) === s.trump);
      pair.appendChild(pc);
    }
    box.appendChild(pair);
    if (p.open) renderTransferSlot(pair, s);
  });
}

/* slot ⟳ del trasferimento, accanto alla coppia con l'attacco aperto */
function renderTransferSlot(pairEl, s) {
  const slot = document.createElement('div');
  slot.className = 'tslot';
  slot.title = 'Trasferisci l\'attacco: gioca una carta dello stesso valore';
  slot.innerHTML = '<span class="rot">↻</span>';
  const actionable = s.phase === 'defend' && s.defender === s.viewer;
  slot.classList.toggle('active', actionable && s.transfer_ranks.length > 0);
  if (!actionable) slot.style.pointerEvents = 'none';
  slot.addEventListener('click', tryTransfer);
  $('#pairs').appendChild(slot);
  requestAnimationFrame(() => {
    slot.style.left = (pairEl.offsetLeft + pairEl.offsetWidth + 8) + 'px';
    slot.style.top = (pairEl.offsetTop + 6) + 'px';
  });
}

function renderHand(s) {
  const hand = $('#hand');
  hand.innerHTML = '';
  const n = s.hand.length;
  const myTurn = isMyTurn(s);
  const order = [...s.hand];
  if (state.sort === 'suit') {
    order.sort((a, b) => (suitOf(a) === suitOf(b) ? RANK_ORDER[rankOf(a)] - RANK_ORDER[rankOf(b)] : 'SCDH'.indexOf(suitOf(a)) - 'SCDH'.indexOf(suitOf(b))));
  }
  order.forEach((c, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'hcard';
    wrap.dataset.id = 'wrap-' + c;
    wrap.style.setProperty('--i', i - (n - 1) / 2);
    const card = document.createElement('div');
    card.className = 'card' + (suitOf(c) === s.trump ? ' trump' : '');
    card.dataset.id = 'c-' + c;
    card.innerHTML = Cards.face(c, suitOf(c) === s.trump);
    wrap.appendChild(card);
    if (!myTurn) wrap.classList.add('dim');
    wrap.addEventListener('pointerdown', e => onPointerDown(e, c, wrap));
    wrap.addEventListener('pointermove', onPointerMove);
    wrap.addEventListener('pointerup', e => onPointerUp(e, c, wrap));
    wrap.addEventListener('dblclick', () => onCardDbl(c));
    hand.appendChild(wrap);
  });
  if (state.selected && s.hand.includes(state.selected)) {
    const w = hand.querySelector(`[data-id="wrap-${state.selected}"]`);
    if (w) w.classList.add('lifted');
  }
}

function renderActions(s) {
  const myTurn = isMyTurn(s);
  $('#app').classList.toggle('my-turn', myTurn);
  const take = $('#take-btn');
  const pass = $('#pass-btn');
  take.hidden = !s.can_take;
  pass.hidden = !s.can_pass;
  // in attack il pulsante chiude l'attacco multi-carta; in throw_in finisce il giro
  pass.textContent = s.phase === 'attack' ? 'Done ✓' : 'Enough';

  let status;
  if (s.phase === 'over') status = '';
  else if (!myTurn) status = `«${s.opp_name}» is thinking…`;
  else if (s.phase === 'attack') {
    status = s.table.length
      ? 'Your turn: play more cards of the same rank or press «Done»'
      : 'Your turn: pick a card to attack (you can play several of the same rank)';
  } else if (s.phase === 'defend') {
    status = s.transfer_ranks.length
      ? 'Your turn: beat (tap a card, then the pair), transfer with the same rank, or take'
      : 'Your turn: beat the card or take';
  } else if (s.phase === 'throw_in') status = 'Your turn: throw a matching card or press «Enough»';
  $('#status-line').textContent = status;
}

function renderOverlay(s) {
  const ov = $('#overlay');
  const title = $('#overlay-title');
  const sub = $('#overlay-sub');
  const spinner = $('#overlay-spinner');
  const rematch = $('#rematch-btn');
  const emblem = $('#overlay-emblem');

  if (!s.started) {
    ov.hidden = false;
    emblem.textContent = '🎴';
    title.textContent = 'Room created';
    title.className = '';
    sub.textContent = 'Waiting for your opponent…\nThe game starts as soon as they join.';
    spinner.hidden = false;
    rematch.hidden = true;
    return;
  }
  if (s.phase !== 'over') { ov.hidden = true; return; }

  ov.hidden = false;
  spinner.hidden = true;
  rematch.hidden = false;
  const won = s.winner === s.viewer;
  const drew = s.winner === -1;
  emblem.textContent = won ? '🏆' : drew ? '🤝' : '😅';
  title.textContent = s.abandoned ? 'Opponent disconnected' : won ? 'You won!' : drew ? 'Draw' : 'You are the Durak!';
  title.className = won || s.abandoned ? 'win' : 'lose';
  sub.textContent = s.abandoned
    ? 'Your opponent lost connection: game over.'
    : won ? '«' + s.opp_name + '» is the durak this round. 🎉'
    : drew ? 'Both out of cards: no durak.'
    : '«' + s.opp_name + '» ran out of cards before you. Rematch?';
}

/* ============================== interazioni ============================== */

/* Gioca la carta secondo la fase: attacco, lancio, trasferimento o battuta.
   `targetIdx` (opzionale) è l'indice della coppia da battere, scelto con il
   drag-drop direttamente su quella coppia. Ritorna true se la mossa è
   stata inviata. */
function resolvePlay(c, wrap, targetIdx) {
  const s = state.s;
  if (!s || s.phase === 'over') return false;
  const mine = s.viewer;

  if (s.phase === 'attack' && s.attacker === mine) {
    // la prima carta è libera; le successive devono avere un valore già sul
    // tavolo (regola переводной: apertura con due carte dello stesso valore)
    if (s.table.length && !tableRanks(s).has(rankOf(c))) {
      toast('You can only play cards matching a rank on the table', true);
      shakeWrap(wrap);
      return false;
    }
    send({ type: 'play', card: c });
    return true;
  }
  if (s.phase === 'throw_in' && s.attacker === mine) {
    if (s.defender_empty) {
      toast('The defender has no cards: press «Enough»', true);
      return false;
    }
    if (tableRanks(s).has(rankOf(c))) { send({ type: 'play', card: c }); return true; }
    toast('You can only throw cards matching a rank on the table', true);
    shakeWrap(wrap);
    return false;
  }
  if (s.phase === 'defend' && s.defender === mine) {
    const open = s.table.find(p => p.open);
    if (open && s.transfer_ranks.includes(rankOf(c))) {
      send({ type: 'transfer', card: c });
      return true;
    }
    // con più attacchi aperti si può scegliere QUALE battere (es. la coppia
    // a destra): il target è l'indice della coppia sotto il dito
    if (targetIdx != null) {
      const pair = s.table[targetIdx];
      if (pair && pair.open && beatsCard(c, pair.stack[pair.stack.length - 1], s.trump)) {
        send({ type: 'beat', card: c, target: targetIdx });
        return true;
      }
      toast("That card doesn't beat that attack", true);
      shakeWrap(wrap);
      return false;
    }
    if (open && beatsCard(c, open.stack[open.stack.length - 1], s.trump)) {
      send({ type: 'beat', card: c });
      return true;
    }
    toast("That card doesn't beat the attack", true);
    shakeWrap(wrap);
    return false;
  }
  return false;
}

function shakeWrap(wrap) {
  wrap.classList.add('shake');
  setTimeout(() => wrap.classList.remove('shake'), 350);
}

/* ---- drag & drop: la carta segue il dito, il rilascio sul tavolo gioca ---- */
let drag = null;
let suppressClick = false;

function onPointerDown(e, c, wrap) {
  const s = state.s;
  if (!s || s.phase === 'over' || !isMyTurn(s)) return;
  if (e.pointerType === 'mouse' && e.button !== 0) return;
  drag = { card: c, wrap, clone: null, x: e.clientX, y: e.clientY, moved: false, offX: 0, offY: 0 };
  try { wrap.setPointerCapture(e.pointerId); } catch { /* ok */ }
}

function onPointerMove(e) {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (!drag.moved && Math.hypot(dx, dy) > 8) {
    drag.moved = true;
    const r = drag.wrap.getBoundingClientRect();
    drag.offX = r.width / 2;
    drag.offY = r.height / 2;
    drag.clone = document.createElement('div');
    drag.clone.className = 'drag-card';
    drag.clone.innerHTML = Cards.face(drag.card, suitOf(drag.card) === state.s.trump);
    drag.clone.style.width = r.width + 'px';
    drag.clone.style.height = r.height + 'px';
    document.body.appendChild(drag.clone);
    drag.wrap.classList.add('dragging');
  }
  if (drag.moved && drag.clone) {
    drag.clone.style.left = (e.clientX - drag.offX) + 'px';
    drag.clone.style.top = (e.clientY - drag.offY) + 'px';
  }
}

function onPointerUp(e, c, wrap) {
  if (!drag) return;
  const wasDrag = drag.moved;
  const clone = drag.clone;
  drag = null;
  wrap.classList.remove('dragging');
  if (!wasDrag) {
    // tocco semplice: comportamento click (selezione o trasferimento)
    onCardClick(c, wrap);
    return;
  }
  suppressClick = true;
  setTimeout(() => { suppressClick = false; }, 80);
  if (!clone) return;
  const el = document.elementFromPoint(e.clientX, e.clientY);
  const overTable = el && el.closest('#pairs, #lane');
  if (overTable) {
    clone.remove();
    // se il rilascio è su una coppia specifica, si batte QUELLA
    const pairEl = el.closest('.pair');
    resolvePlay(c, wrap, pairEl ? +pairEl.dataset.idx : undefined);
    return;
  }
  // rilascio fuori dal tavolo: la carta torna al suo posto
  const wr = wrap.getBoundingClientRect();
  const cr = clone.getBoundingClientRect();
  clone.animate([
    { transform: 'none', opacity: 1 },
    {
      transform: `translate(${wr.left + wr.width / 2 - (cr.left + cr.width / 2)}px, ${wr.top + wr.height / 2 - (cr.top + cr.height / 2)}px) scale(.7)`,
      opacity: 0,
    },
  ], { duration: 230, easing: 'ease-in' }).onfinish = () => clone.remove();
}

function onCardClick(c, wrap) {
  const s = state.s;
  if (!s || s.phase === 'over') return;
  const mine = s.viewer;

  if (s.phase === 'attack' && s.attacker === mine) {
    resolvePlay(c, wrap);
    return;
  }
  if (s.phase === 'throw_in' && s.attacker === mine) {
    resolvePlay(c, wrap);
    return;
  }
  if (s.phase === 'defend' && s.defender === mine) {
    // trasferimento con UN tocco: carta dello stesso valore dell'attacco
    // aperto → l'attacco passa all'avversario (regola переводной)
    const open = s.table.find(p => p.open);
    if (open && s.transfer_ranks.includes(rankOf(c))) {
      resolvePlay(c, wrap);
      return;
    }
    // carta che batte: selezione, poi un tocco sulla coppia per confermare
    if (state.selected === c) {
      state.selected = null;
      wrap.classList.remove('lifted');
    } else {
      state.selected = c;
      document.querySelectorAll('.hcard.lifted').forEach(e => e.classList.remove('lifted'));
      wrap.classList.add('lifted');
    }
  }
}

function onCardDbl(c) {
  // il trasferimento ora avviene con un tocco singolo (onCardClick);
  // il doppio tocco resta come fallback per il beat immediato
  const s = state.s;
  if (!s || s.phase !== 'defend' || s.defender !== s.viewer) return;
  const open = s.table.find(p => p.open);
  if (open && beatsCard(c, open.stack[open.stack.length - 1], s.trump)) {
    send({ type: 'beat', card: c });
  }
}

function tryTransfer() {
  const s = state.s;
  if (!s || s.phase !== 'defend' || s.defender !== s.viewer) return;
  let card = state.selected;
  if (!card || !s.transfer_ranks.includes(rankOf(card))) {
    card = s.hand.find(c => s.transfer_ranks.includes(rankOf(c)));
  }
  if (!card) { toast('You need a card of the same rank to transfer', true); return; }
  state.selected = null;
  send({ type: 'transfer', card });
}

function wireButtons() {
  $('#take-btn').addEventListener('click', () => {
    if (state.s && state.s.can_take) send({ type: 'take' });
  });
  $('#pass-btn').addEventListener('click', () => {
    if (state.s && state.s.can_pass) send({ type: 'pass' });
  });
  $('#sort-btn').addEventListener('click', () => {
    state.sort = state.sort === 'rank' ? 'suit' : 'rank';
    if (state.s) renderHand(state.s);
  });
  $('#rematch-btn').addEventListener('click', () => send({ type: 'rematch' }));
  $('#leave-btn').addEventListener('click', () => {
    if (confirm('Leave the game?')) {
      if (state.conn) state.conn.close();
    }
  });
  $('#pairs').addEventListener('click', e => {
    const pairEl = e.target.closest('.pair');
    const s = state.s;
    if (!pairEl || !s || s.phase !== 'defend' || s.defender !== s.viewer) return;
    if (!pairEl.classList.contains('open')) return;
    if (!state.selected) { toast('Select a card to beat with'); return; }
    // la coppia cliccata è il TARGET (non la prima aperta): con due attacchi
    // sul tavolo il giocatore decide quale battere (es. quello a destra)
    const idx = +pairEl.dataset.idx;
    const target = s.table[idx];
    if (!target || !target.open || !beatsCard(state.selected, target.stack[target.stack.length - 1], s.trump)) {
      toast("That card doesn't beat that attack", true);
      return;
    }
    send({ type: 'beat', card: state.selected, target: idx });
  });
}

/* ============================== toast e timer ============================== */

function toast(text, isErr) {
  const t = document.createElement('div');
  t.className = 'toast' + (isErr ? ' err' : '');
  t.textContent = text;
  $('#toasts').appendChild(t);
  setTimeout(() => {
    t.style.transition = 'opacity .35s, transform .35s';
    t.style.opacity = '0';
    t.style.transform = 'translateY(-8px)';
    setTimeout(() => t.remove(), 380);
  }, 2600);
}

function eventToasts(s) {
  const prev = state.prevS;
  if (!prev || (prev.phase === s.phase && prev.last_action === s.last_action)) return;
  const prevN = prev.table.length
    ? prev.table.reduce((a, p) => a + p.stack.length + (p.defense ? 1 : 0), 0) : 0;
  switch (s.last_action) {
    case 'take':
      toast((s.defender === s.viewer ? 'You took ' : '«' + s.opp_name + '» took ') + prevN + ' cards');
      break;
    case 'clear': toast('Round cleared'); break;
    case 'transfer':
      toast(s.viewer === s.attacker
        ? 'Transfer! The attack goes back to «' + s.opp_name + '»'
        : '«' + s.opp_name + '» transferred the attack: your turn to defend');
      break;
  }
}

/* anello del timer: attivo sul chip di chi deve muovere.
   Durata allineata a TURN_TIME del server (45s); allo scadere l'anello
   resta fermo — il turno NON viene saltato automaticamente. */
const TURN_SECONDS = 45;
let lastRingOwner = null;
function timerLoop() {
  const s = state.s;
  const C = 131.9;
  const myTurn = s && isMyTurn(s);
  const owner = s ? (myTurn ? 'me' : 'opp') : null;
  const ring = owner === 'me' ? $('#me-chip .ring') : $('#opp-chip .ring');
  const other = owner === 'me' ? $('#opp-chip .ring') : $('#me-chip .ring');
  if (owner) {
    ring.classList.remove('idle');
    other.classList.add('idle');
    if (s.deadline) {
      const frac = Math.max(0, Math.min(1, (s.deadline - Date.now() / 1000) / TURN_SECONDS));
      const fg = ring.querySelector('.ring-fg');
      fg.style.strokeDashoffset = String(C * (1 - frac));
      ring.classList.toggle('urgent', frac < 0.17);
    }
  }
  requestAnimationFrame(timerLoop);
}

/* ============================== avvio ============================== */

const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  tg.expand();
  tg.ready();
  if (tg.setHeaderColor) tg.setHeaderColor('#070d15');
  if (tg.setBackgroundColor) tg.setBackgroundColor('#070d15');
}

wireButtons();
connect();
requestAnimationFrame(timerLoop);

// hook di debug (devtools): window.__durak.state() → stato corrente
window.__durak = { state: () => state.s };
})();
