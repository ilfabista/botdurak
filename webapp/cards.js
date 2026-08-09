/* cards.js — carte francesi classiche (pattern di Parigi) in SVG puro.
   Faccia: avorio con doppia cornice (scura + filo d'oro), indici d'angolo,
   pips disposti per rango (6..10), figure in serif con pip, asso ornato.
   Retro: navy con reticolo a losanghe dorate e medaglione. */
(function () {
  'use strict';

  const SYM = { H: '♥', D: '♦', C: '♣', S: '♠' };
  const COLOR = { H: '#b91d2e', D: '#b91d2e', C: '#20242e', S: '#20242e' };
  const GOLD = '#c9a24b';
  const INK = '#2b3040';
  let uid = 0;

  /* layout classico dei pips per le carte numeriche (coordinate in viewBox
     0..100 × 0..140): righe alternate su due colonne */
  const PIP_X = [32, 68];
  function pipRows(rank) {
    const rows = {
      6: [[0, 52], [1, 52], [0, 78], [1, 78], [0, 104], [1, 104]],
      7: [[0, 50], [1, 50], [0, 76], [1, 76], [0, 102], [1, 102], [0.5, 38]],
      8: [[0, 46], [1, 46], [0, 70], [1, 70], [0, 94], [1, 94], [0, 118], [1, 118]],
      9: [[0.5, 40], [0, 62], [1, 62], [0, 86], [1, 86], [0, 110], [1, 110], [0.5, 88], [0.5, 122]],
      10: [[0, 42], [1, 42], [0, 62], [1, 62], [0, 82], [1, 82], [0, 102], [1, 102], [0, 120], [1, 120]],
    };
    return rows[rank] || [];
  }
  function pipsHtml(rank, s, color) {
    let rows = pipRows(rank);
    // le righe in verticale: i pips inferiori specchiati? No: pattern a
    // doppia testa — stessa disposizione sopra e sotto, con i pips bassi
    // ruotati di 180° come nelle carte francesi (per leggibilità).
    const parts = [];
    const n = rows.length;
    const mirrored = [3, 4, 5, 6, 7, 8, 9, 10].includes(rank);
    const half = Math.ceil(n / 2);
    rows.forEach((r, i) => {
      const x = PIP_X[r[0] === 0.5 ? 0 : r[0]];
      let y = r[1];
      const flip = mirrored && i >= half;
      if (flip) {
        // il pip specchiato si calcola per simmetria sul centro carta (y=70)
        y = 140 - y;
      }
      const rot = flip ? ' transform="rotate(180 ' + x + ' ' + y + ')"' : '';
      parts.push(`<text x="${x}" y="${y + 6}" font-size="17" text-anchor="middle" fill="${color}"${rot}>${SYM[s]}</text>`);
    });
    return parts.join('\n      ');
  }

  function corner(x, y, flip, label, s, color) {
    const size = label.length > 1 ? 18 : 23;
    const sy = flip ? y - 20 : y + 19;
    const g = flip
      ? `<g transform="translate(${x} ${y}) rotate(180)">`
      : `<g>`;
    return `${g}
      <text x="0" y="${flip ? 0 : y}" font-size="${size}" font-weight="800" fill="${color}" font-family="Georgia, 'Times New Roman', serif">${label}</text>
      <text x="0" y="${flip ? -19 : sy}" font-size="13.5" fill="${color}">${SYM[s]}</text>
    </g>`;
  }

  function face(card, isTrump) {
    const r = card[0], s = card[1], color = COLOR[s];
    const label = r === 'T' ? '10' : r;
    const id = 'durak' + (++uid);
    let center;
    if (r === 'A') {
      // asso: pip grande con doppio anello ornamentale
      center = `
        <circle cx="50" cy="70" r="31" fill="none" stroke="${color}" stroke-opacity=".28" stroke-width="1.1"/>
        <circle cx="50" cy="70" r="25.5" fill="none" stroke="${color}" stroke-opacity=".18" stroke-width=".8"/>
        <text x="50" y="88" font-size="52" font-weight="700" text-anchor="middle" fill="${color}" font-family="Georgia, serif">${SYM[s]}</text>`;
    } else if ('JQK'.includes(r)) {
      // figure: monogramma in serif dentro una ghirlanda a doppio ovale
      const orn = s === 'C' || s === 'S' ? '♣' : SYM[s];
      center = `
        <path d="M50 30 C 74 38, 74 102, 50 110 C 26 102, 26 38, 50 30 Z" fill="none" stroke="${color}" stroke-opacity=".22" stroke-width="1.2"/>
        <path d="M50 35 C 70 42, 70 98, 50 105 C 30 98, 30 42, 50 35 Z" fill="none" stroke="${color}" stroke-opacity=".12" stroke-width=".9"/>
        <text x="50" y="86" font-size="46" font-weight="700" text-anchor="middle" fill="${color}" font-family="Georgia, 'Times New Roman', serif" font-style="italic">${label}</text>
        <text x="50" y="112" font-size="16" text-anchor="middle" fill="${color}">${SYM[s]}</text>
        <text x="50" y="33" font-size="10" text-anchor="middle" fill="${color}" fill-opacity=".55">${orn}</text>`;
    } else {
      center = pipsHtml(r, s, color);
    }
    const trumpMark = isTrump ? `
      <rect x="3.4" y="3.4" width="93.2" height="133.2" rx="9" fill="none" stroke="${GOLD}" stroke-width="2.4"/>
      <path d="M50 14 l2.6 5 5 2.6 -5 2.6 -2.6 5 -2.6 -5 -5 -2.6 5 -2.6 Z" fill="${GOLD}"/>` : '';
    return `<svg class="card-svg" viewBox="0 0 100 140" xmlns="http://www.w3.org/2000/svg" aria-label="${label} ${SYM[s]}">
      <defs>
        <linearGradient id="${id}f" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#fffefb"/><stop offset="1" stop-color="#f2ecdd"/>
        </linearGradient>
      </defs>
      <rect x="1.5" y="1.5" width="97" height="137" rx="11" fill="url(#${id}f)" stroke="${INK}" stroke-width="1.2"/>
      <rect x="5" y="5" width="90" height="130" rx="8" fill="none" stroke="${GOLD}" stroke-opacity=".8" stroke-width="1"/>
      <rect x="7.2" y="7.2" width="85.6" height="125.6" rx="6.5" fill="none" stroke="#c9c2ae" stroke-opacity=".6" stroke-width=".7"/>
      ${trumpMark}
      ${corner(11, 28, false, label, s, color)}
      ${corner(91, 98, true, label, s, color)}
      ${center}
    </svg>`;
  }

  function back() {
    const id = 'durakb' + (++uid);
    return `<svg class="card-svg" viewBox="0 0 100 140" xmlns="http://www.w3.org/2000/svg" aria-label="carta coperta">
      <defs>
        <linearGradient id="${id}g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#1c2b45"/><stop offset="1" stop-color="#0a1322"/>
        </linearGradient>
        <pattern id="${id}p" width="14" height="14" patternUnits="userSpaceOnUse">
          <path d="M7 0 L14 7 L7 14 L0 7 Z" fill="none" stroke="${GOLD}" stroke-opacity=".16" stroke-width=".9"/>
        </pattern>
      </defs>
      <rect x="1.5" y="1.5" width="97" height="137" rx="11" fill="url(#${id}g)" stroke="#31456a" stroke-width="1.3"/>
      <rect x="6" y="6" width="88" height="128" rx="8" fill="url(#${id}p)"/>
      <rect x="6" y="6" width="88" height="128" rx="8" fill="none" stroke="${GOLD}" stroke-opacity=".5" stroke-width="1.1"/>
      <rect x="11" y="11" width="78" height="118" rx="6" fill="none" stroke="${GOLD}" stroke-opacity=".22" stroke-width=".8"/>
      <path d="M50 44 l10.5 17.5 17.5 10.5 -17.5 10.5 -10.5 17.5 -10.5 -17.5 -17.5 -10.5 17.5 -10.5 Z" fill="${GOLD}" fill-opacity=".9"/>
      <path d="M50 52 l6 10 10 6 -10 6 -6 10 -6 -10 -10 -6 10 -6 Z" fill="#0a1322" fill-opacity=".55"/>
      <circle cx="50" cy="78" r="2.6" fill="${GOLD}"/>
    </svg>`;
  }

  window.Cards = { face: face, back: back, SYM: SYM };
})();
