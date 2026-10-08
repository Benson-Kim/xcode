// React Native has no WebCrypto, so PBKDF2-HMAC-SHA256 runs here in plain TypeScript.
const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const IV = new Uint32Array([
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
  0x1f83d9ab, 0x5be0cd19,
]);

function compress(state: Uint32Array, block: Uint32Array, w: Uint32Array) {
  w.set(block);
  for (let i = 16; i < 64; i++) {
    const x = w[i - 15];
    const y = w[i - 2];
    const s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
    const s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  let a = state[0];
  let b = state[1];
  let c = state[2];
  let d = state[3];
  let e = state[4];
  let f = state[5];
  let g = state[6];
  let h = state[7];
  for (let i = 0; i < 64; i++) {
    const s1 =
      ((e >>> 6) | (e << 26)) ^
      ((e >>> 11) | (e << 21)) ^
      ((e >>> 25) | (e << 7));
    const t1 = (h + s1 + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0;
    const s0 =
      ((a >>> 2) | (a << 30)) ^
      ((a >>> 13) | (a << 19)) ^
      ((a >>> 22) | (a << 10));
    const t2 = (s0 + ((a & b) ^ (a & c) ^ (b & c))) | 0;
    h = g;
    g = f;
    f = e;
    e = (d + t1) | 0;
    d = c;
    c = b;
    b = a;
    a = (t1 + t2) | 0;
  }
  state[0] += a;
  state[1] += b;
  state[2] += c;
  state[3] += d;
  state[4] += e;
  state[5] += f;
  state[6] += g;
  state[7] += h;
}

function hash(
  initial: Uint32Array,
  prefix: number,
  data: Uint8Array,
  w: Uint32Array,
) {
  const state = initial.slice();
  const length = Math.ceil((data.length + 9) / 64) * 64;
  const padded = new Uint8Array(length);
  padded.set(data);
  padded[data.length] = 0x80;
  const view = new DataView(padded.buffer);
  const bits = (prefix + data.length) * 8;
  view.setUint32(length - 8, Math.floor(bits / 0x100000000));
  view.setUint32(length - 4, bits >>> 0);
  const block = new Uint32Array(16);
  for (let offset = 0; offset < length; offset += 64) {
    for (let i = 0; i < 16; i++) block[i] = view.getUint32(offset + i * 4);
    compress(state, block, w);
  }
  return state;
}

function bytes(words: Uint32Array) {
  const out = new Uint8Array(words.length * 4);
  const view = new DataView(out.buffer);
  words.forEach((word, i) => view.setUint32(i * 4, word));
  return out;
}

export function pbkdf2Sha256(
  password: Uint8Array,
  salt: Uint8Array,
  iterations: number,
): Uint8Array {
  const w = new Uint32Array(64);
  const key = new Uint8Array(64);
  key.set(password.length > 64 ? bytes(hash(IV, 0, password, w)) : password);
  const keyView = new DataView(key.buffer);
  const pad = new Uint32Array(16);
  const inner = IV.slice();
  const outer = IV.slice();
  for (let i = 0; i < 16; i++) pad[i] = keyView.getUint32(i * 4) ^ 0x36363636;
  compress(inner, pad, w);
  for (let i = 0; i < 16; i++) pad[i] = keyView.getUint32(i * 4) ^ 0x5c5c5c5c;
  compress(outer, pad, w);

  const first = new Uint8Array(salt.length + 4);
  first.set(salt);
  first[salt.length + 3] = 1;
  const u = hash(outer, 64, bytes(hash(inner, 64, first, w)), w);
  const result = u.slice();
  const block = new Uint32Array(16);
  block[8] = 0x80000000;
  block[15] = (64 + 32) * 8;
  const state = new Uint32Array(8);
  for (let n = 1; n < iterations; n++) {
    block.set(u);
    state.set(inner);
    compress(state, block, w);
    block.set(state);
    u.set(outer);
    compress(u, block, w);
    for (let i = 0; i < 8; i++) result[i] ^= u[i];
  }
  return bytes(result);
}
