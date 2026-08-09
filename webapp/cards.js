/* cards.js — carte da gioco in SVG puro, design moderno flat.
   Facce: cartoncino avorio con gradiente sottile, angoli con valore e seme,
   al centro il seme (carte numeriche) o monogramma (figure). Briscola con
   filo d'oro. Retro: navy profondo con reticolo di diamanti dorati. */
(function () {
  'use strict';

  const SYM = { H: '♥', D: '♦', C: '♣', S: '♠' };
  const COLOR = { H: '#c0394f', D: '#c0394f', C: '#26334d', S: '#26334d' };
  const GOLD = '#c9a24b';
  let uid = 0;

  function corner(x, y, flip, label, s, color) {
    // Angolo in alto a sinistra (flip=false): testo che parte da (x,y) verso
    // destra/basso. Angolo in basso a destra (flip=true): gruppo ruotato di
    // 180° con origine vicina all'angolo: il testo (anchor start) si estende
    // verso sinistra e "in giù" verso il bordo, risultando specchiato.
    const size = label.length > 1 ? 19 : 26;
    const sy = flip ? y - 20 : y + 20;
    const g = flip
      ? `<g transform="translate(${x} ${y}) rotate(180)">`
      : `<g>`;
    return `${g}
      <text x="0" y="${flip ? 0 : y}" font-size="${size}" font-weight="800" fill="${color}" font-family="Inter, system-ui, sans-serif">${label}</text>
      <text x="0" y="${flip ? -20 : sy}" font-size="15" fill="${color}">${SYM[s]}</text>
    </g>`;
  }

  function face(card, isTrump) {
    const r = card[0], s = card[1], color = COLOR[s];
    const label = r === 'T' ? '10' : r;
    const isFigure = 'JQKA'.includes(r);
    const id = 'durak' + (++uid);
    let center;
    if (isFigure) {
      center = `
        <circle cx="50" cy="76" r="30" fill="none" stroke="${color}" stroke-opacity=".25" stroke-width="1.6"/>
        <text x="50" y="90" font-size="42" font-weight="700" text-anchor="middle" fill="${color}"
              font-family="Georgia, 'Times New Roman', serif">${label}</text>
        <text x="50" y="110" font-size="14" text-anchor="middle" fill="${color}">${SYM[s]}</text>`;
    } else {
      center = `
        <circle cx="50" cy="78" r="33" fill="${color}" fill-opacity=".06"/>
        <text x="50" y="95" font-size="50" text-anchor="middle" fill="${color}">${SYM[s]}</text>`;
    }
    const trumpMark = isTrump ? `
      <rect x="2.4" y="2.4" width="95.2" height="135.2" rx="10" fill="none" stroke="${GOLD}" stroke-width="2.2"/>
      <path d="M50 12 l3 5.6 5.6 3 -5.6 3 -3 5.6 -3 -5.6 -5.6 -3 5.6 -3 Z" fill="${GOLD}"/>` : '';
    return `<svg class="card-svg" viewBox="0 0 100 140" xmlns="http://www.w3.org/2000/svg" aria-label="${label} ${SYM[s]}">
      <defs>
        <linearGradient id="${id}f" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#fcf9f2"/><stop offset="1" stop-color="#eae1cc"/>
        </linearGradient>
      </defs>
      <rect x="1.5" y="1.5" width="97" height="137" rx="11" fill="url(#${id}f)" stroke="#d4cab2" stroke-width="1.3"/>
      <rect x="5.5" y="5.5" width="89" height="129" rx="8" fill="none" stroke="#f2ecdd" stroke-width="1"/>
      ${trumpMark}
      ${corner(10, 30, false, label, s, color)}
      ${corner(92, 96, true, label, s, color)}
      ${center}
    </svg>`;
  }

  function back() {
    const id = 'durakb' + (++uid);
    return `<svg class="card-svg" viewBox="0 0 100 140" xmlns="http://www.w3.org/2000/svg" aria-label="carta coperta">
      <defs>
        <linearGradient id="${id}g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#1b2c47"/><stop offset="1" stop-color="#0a1322"/>
        </linearGradient>
        <pattern id="${id}p" width="16" height="16" patternUnits="userSpaceOnUse">
          <path d="M8 0 L16 8 L8 16 L0 8 Z" fill="none" stroke="${GOLD}" stroke-opacity=".20" stroke-width="1"/>
        </pattern>
      </defs>
      <rect x="1.5" y="1.5" width="97" height="137" rx="11" fill="url(#${id}g)" stroke="#31456a" stroke-width="1.3"/>
      <rect x="7" y="7" width="86" height="126" rx="8" fill="url(#${id}p)"/>
      <rect x="24" y="40" width="52" height="60" rx="4" fill="none" stroke="${GOLD}" stroke-opacity=".65" stroke-width="1.5"/>
      <path d="M50 47 l7.5 12.5 12.5 7.5 -12.5 7.5 -7.5 12.5 -7.5 -12.5 -12.5 -7.5 12.5 -7.5 Z" fill="${GOLD}" fill-opacity=".85"/>
    </svg>`;
  }

  window.Cards = { face: face, back: back, SYM: SYM };
})();
