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
    expect(hex(await pbkdf2Sha256(password, salt, iterations))).toBe(
      hex(await webCrypto(password, salt, iterations)),
    );
  },
);

it("hands the thread back between slices, so the screen keeps responding while it derives", async () => {
  let slices = 0;
  let tick: ReturnType<typeof setTimeout>;
  const count = () => {
    slices++;
    tick = setTimeout(count, 0);
  };
  tick = setTimeout(count, 0);
  try {
    const salt = new Uint8Array(16).fill(3);
    const password = new TextEncoder().encode("1379");
    const sliced = await pbkdf2Sha256(password, salt, 5000, 0);
    expect(slices).toBeGreaterThan(10);
    expect(hex(sliced)).toBe(hex(await webCrypto(password, salt, 5000)));
  } finally {
    clearTimeout(tick!);
  }
});
