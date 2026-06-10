/* Gera os ícones PNG do PWA (180/192/512) sem dependências externas.
 * Uso: node tools/gen-icons.mjs
 */
import { deflateSync, crc32 } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..');
const destino = join(raiz, 'app', 'icons');
mkdirSync(destino, { recursive: true });

const CORES = {
  fundo: [0x00, 0x7e, 0x7a],
  branco: [0xff, 0xff, 0xff],
  montanha: [0x00, 0x7e, 0x7a],
  montanha2: [0x3a, 0xa3, 0x9e],
  sol: [0xed, 0xb1, 0x11],
};

function dentroRetArred(px, py, x, y, w, h, r) {
  if (px < x || px > x + w || py < y || py > y + h) return false;
  const cx = Math.max(x + r, Math.min(px, x + w - r));
  const cy = Math.max(y + r, Math.min(py, y + h - r));
  const dx = px - cx;
  const dy = py - cy;
  return dx * dx + dy * dy <= r * r || (px >= x + r && px <= x + w - r) || (py >= y + r && py <= y + h - r);
}

function dentroTriangulo(px, py, [ax, ay], [bx, by], [cx, cy]) {
  const sinal = (x1, y1, x2, y2, x3, y3) => (x1 - x3) * (y2 - y3) - (x2 - x3) * (y1 - y3);
  const d1 = sinal(px, py, ax, ay, bx, by);
  const d2 = sinal(px, py, bx, by, cx, cy);
  const d3 = sinal(px, py, cx, cy, ax, ay);
  const neg = (d1 < 0) || (d2 < 0) || (d3 < 0);
  const pos = (d1 > 0) || (d2 > 0) || (d3 > 0);
  return !(neg && pos);
}

function dentroCirculo(px, py, cx, cy, r) {
  const dx = px - cx;
  const dy = py - cy;
  return dx * dx + dy * dy <= r * r;
}

/* Mesma arte do icon.svg, em coordenadas relativas (base 512). */
function corDoPixel(px, py, s) {
  const k = s / 512;
  let cor = CORES.fundo;
  const balao = dentroRetArred(px, py, 66 * k, 102 * k, 380 * k, 216 * k, 26 * k);
  const cauda = dentroTriangulo(px, py, [154 * k, 300 * k], [214 * k, 318 * k], [154 * k, 380 * k]);
  if (balao || cauda) {
    cor = CORES.branco;
    if (dentroTriangulo(px, py, [124 * k, 286 * k], [216 * k, 164 * k], [304 * k, 286 * k])) cor = CORES.montanha;
    if (dentroTriangulo(px, py, [236 * k, 286 * k], [328 * k, 178 * k], [400 * k, 286 * k])) cor = CORES.montanha2;
    if (dentroCirculo(px, py, 356 * k, 156 * k, 30 * k)) cor = CORES.sol;
  }
  return cor;
}

function chunk(tipo, dados) {
  const corpo = Buffer.concat([Buffer.from(tipo, 'ascii'), dados]);
  const tamanho = Buffer.alloc(4);
  tamanho.writeUInt32BE(dados.length);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(corpo) >>> 0);
  return Buffer.concat([tamanho, corpo, crc]);
}

function gerarPNG(s) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(s, 0);
  ihdr.writeUInt32BE(s, 4);
  ihdr[8] = 8;  // 8 bits por canal
  ihdr[9] = 2;  // RGB

  const linhas = Buffer.alloc(s * (1 + s * 3));
  for (let y = 0; y < s; y++) {
    const base = y * (1 + s * 3);
    linhas[base] = 0; // filtro "none"
    for (let x = 0; x < s; x++) {
      const [r, g, b] = corDoPixel(x + 0.5, y + 0.5, s);
      const i = base + 1 + x * 3;
      linhas[i] = r;
      linhas[i + 1] = g;
      linhas[i + 2] = b;
    }
  }

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(linhas, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

for (const s of [180, 192, 512]) {
  const arquivo = join(destino, `icon-${s}.png`);
  writeFileSync(arquivo, gerarPNG(s));
  console.log('gerado', arquivo);
}
