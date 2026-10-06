import { pbkdf2Sha256 } from "../src/lib/pbkdf2";

jest.unmock("../src/lib/pbkdf2");

const hex = (bytes: Uint8Array) =>
  Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");

async function webCrypto(
  password: Uint8Array<ArrayBuffer>,
  salt: Uint8Array<ArrayBuffer>,
  iterations: number,
) {
  const key = await crypto.subtle.importKey("raw", password, "PBKDF2", false, [
    "deriveBits",
  ]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    key,
    256,
  );
  return new Uint8Array(bits);
}

it.each([
  ["5826", 16, 1],
  ["5826", 16, 2],
  ["13790246", 16, 1000],
  ["2580", 60, 3],
  ["9".repeat(65), 16, 2],
  ["1379", 16, 100_000],
])(
  "derives what WebCrypto derives for PIN %s with a %i-byte salt over %i iterations",
  async (pin, saltLength, iterations) => {
    const password = new TextEncoder().encode(pin);
    const salt = Uint8Array.from(
      { length: saltLength },
      (_, i) => (i * 37 + 11) & 0xff,
    );
    expect(hex(pbkdf2Sha256(password, salt, iterations))).toBe(
      hex(await webCrypto(password, salt, iterations)),
    );
  },
);
