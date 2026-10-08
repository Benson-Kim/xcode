import {
  initialState,
  limitsOf,
  padCopy,
  reduce,
  trustedHere,
  type Action,
  type AuthState,
  type PadScreen,
} from "../src/auth/authFlowState";
import type { StoredPerson } from "../src/lib/storage";

const person: StoredPerson = {
  userId: "u1",
  phoneNumber: "0733520614",
  firstName: "Antony",
  lastName: "Mwangi",
  role: "Owner",
  permissions: [],
  pinLength: 4,
  lockoutThreshold: 3,
  lockoutMinutes: 10,
};

const run = (state: AuthState, ...actions: Action[]) =>
  actions.reduce(reduce, state);

const fresh = () => initialState(null);
const trusted = () => initialState(person);

const typed = (state: AuthState, pin: string) =>
  run(state, ...[...pin].map((digit): Action => ({ type: "digit", digit })));

const signinCode = (secret: string) =>
  run(
    fresh(),
    { type: "phoneAccepted", phone: "0712345678" },
    { type: "padOpened", mode: "enter" },
    {
      type: "codeRequested",
      flow: "signin",
      challengePin: secret,
      lead: "New phone. ",
      maskedEmail: "w***@example.com",
      developmentCode: "",
    },
  );

const setupCode = () =>
  run(
    fresh(),
    { type: "phoneAccepted", phone: "0700111222" },
    {
      type: "codeRequested",
      flow: "setup",
      lead: "",
      maskedEmail: "",
      developmentCode: "",
    },
  );

const confirming = (chosen: string, code = "918273") =>
  run(
    setupCode(),
    { type: "codeVerified", code },
    { type: "pinChosen", pin: chosen },
  );

const pad = (state: AuthState) => {
  if (state.screen.step !== "pad") throw new Error("not on the pad");
  return state.screen;
};

describe("starting state", () => {
  it("opens a trusted phone on the unlock pad with the person's PIN length", () => {
    const state = initialState({ ...person, pinLength: 6 });
    expect(state.screen).toMatchObject({ step: "pad", mode: "unlock" });
    expect(state.pinLength).toBe(6);
    expect(state.phone).toBe("0733520614");
    expect(trustedHere(state)).toBe(true);
  });

  it("opens an untrusted phone on the number step", () => {
    const state = fresh();
    expect(state.screen).toEqual({ step: "phone", fieldError: "", banner: "" });
    expect(state.pinLength).toBe(4);
    expect(trustedHere(state)).toBe(false);
  });

  it("reads the wrong-PIN limits from the person, else the defaults", () => {
    expect(limitsOf(trusted())).toEqual({
      triesAllowed: 3,
      lockoutSeconds: 600,
    });
    expect(limitsOf(fresh())).toEqual({ triesAllowed: 5, lockoutSeconds: 900 });
    const elsewhere = run(trusted(), {
      type: "phoneAccepted",
      phone: "0712345678",
    });
    expect(limitsOf(elsewhere).triesAllowed).toBe(5);
  });
});

describe("the number step", () => {
  it("keeps what is typed and clears the messages", () => {
    const state = run(
      fresh(),
      { type: "phoneRejected", message: "Enter a valid number." },
      { type: "phoneEdited", input: "0712 345" },
    );
    expect(state.phoneInput).toBe("0712 345");
    expect(state.screen).toEqual({ step: "phone", fieldError: "", banner: "" });
  });

  it("puts a failure from asking for a code in the banner", () => {
    const state = run(fresh(), { type: "errorShown", message: "No internet." });
    expect(state.screen).toMatchObject({
      step: "phone",
      banner: "No internet.",
    });
  });

  it("takes the trusted person's PIN length only for their own number", () => {
    expect(
      run(trusted(), { type: "phoneAccepted", phone: "0733520614" }).pinLength,
    ).toBe(4);
    const six = initialState({ ...person, pinLength: 6 });
    expect(
      run(six, { type: "phoneAccepted", phone: "0733520614" }).pinLength,
    ).toBe(6);
    expect(
      run(six, { type: "phoneAccepted", phone: "0712345678" }).pinLength,
    ).toBe(4);
  });
});

describe("the pad", () => {
  it("ignores a number past the PIN length, and clears the error on a number", () => {
    let state = run(trusted(), { type: "padError", message: "Wrong PIN." });
    expect(pad(state).error).toBe("Wrong PIN.");
    state = typed(state, "48261");
    expect(pad(state).pin).toBe("4826");
    expect(pad(state).error).toBe("");
  });

  it("takes up to eight numbers once a long PIN is chosen", () => {
    const state = typed(
      run(
        fresh(),
        { type: "padOpened", mode: "enter" },
        { type: "longPinChosen" },
      ),
      "123456789",
    );
    expect(pad(state).pin).toBe("12345678");
  });

  it("deletes the last number", () => {
    const state = run(typed(trusted(), "48"), { type: "backspace" });
    expect(pad(state).pin).toBe("4");
  });

  it("empties the pad when an entry is submitted", () => {
    const state = run(typed(trusted(), "4826"), { type: "pinSubmitted" });
    expect(JSON.stringify(state)).not.toContain("4826");
  });

  it("shakes only when asked", () => {
    const quiet = run(trusted(), { type: "padError", message: "x" });
    const shaken = run(trusted(), {
      type: "padError",
      message: "x",
      shake: true,
    });
    expect(quiet.shake).toBe(0);
    expect(shaken.shake).toBe(1);
  });

  it("shows a failure on the pad, or on the paused screen", () => {
    expect(
      pad(run(trusted(), { type: "errorShown", message: "No internet." }))
        .error,
    ).toBe("No internet.");
    const paused = run(
      trusted(),
      { type: "paused", until: 100_000, now: 40_000 },
      { type: "errorShown", message: "No internet." },
    );
    expect(paused.screen).toMatchObject({
      step: "paused",
      error: "No internet.",
    });
  });

  it("names the person on the unlock pad and the number on the enter pad", () => {
    const unlock = padCopy(trusted(), pad(trusted()));
    expect(unlock.header).toMatchObject({
      kind: "person",
      title: "Welcome back, Antony",
      sub: "0733 ••• 614",
    });
    const entering = run(
      fresh(),
      { type: "phoneAccepted", phone: "0712345678" },
      {
        type: "padOpened",
        mode: "enter",
      },
    );
    expect(padCopy(entering, pad(entering)).header).toMatchObject({
      title: "0712 345 678",
      sub: "Enter the PIN for this number",
    });
  });
});

describe("choosing a new PIN", () => {
  it("holds the first entry until it is confirmed", () => {
    const state = confirming("5937");
    expect(pad(state)).toMatchObject({
      mode: "confirm",
      chosen: "5937",
      pin: "",
    });
  });

  it("goes back to choosing, with a shake, when the two entries differ", () => {
    const state = run(confirming("5937"), { type: "pinsDiffer" });
    expect(pad(state)).toMatchObject({
      mode: "choose",
      error: "The two PINs did not match. Choose your PIN again.",
    });
    expect(state.shake).toBe(1);
    expect(JSON.stringify(state)).not.toContain("5937");
  });

  it("starts again without the first entry", () => {
    const state = run(confirming("5937"), { type: "startAgain" });
    expect(pad(state)).toMatchObject({ mode: "choose", error: "" });
    expect(JSON.stringify(state)).not.toContain("5937");
  });

  it("asks for the organization's minimum on the same email code", () => {
    const state = run(confirming("5937", "918273"), {
      type: "pinTooShort",
      minimum: 6,
    });
    expect(pad(state)).toMatchObject({
      mode: "choose",
      flow: "setup",
      code: "918273",
      error: "Your organization needs a PIN of at least 6 numbers.",
    });
    expect(state.pinLength).toBe(6);
    expect(JSON.stringify(state)).not.toContain("5937");
  });

  it("words the choose pad for the flow and the PIN length", () => {
    const state = run(setupCode(), { type: "codeVerified", code: "918273" });
    const copy = padCopy(state, pad(state));
    expect(copy.header).toMatchObject({
      title: "Choose your PIN",
      sub: "Pick 4 numbers only you know. Avoid 1234 or the same number four times.",
    });
    expect(copy.label).toBe("New PIN");
    const confirmed = confirming("5937");
    expect(padCopy(confirmed, pad(confirmed))).toMatchObject({
      label: "Confirm PIN",
      length: 4,
    });
  });
});

describe("the email code", () => {
  it("starts with a full resend wait and no tries used", () => {
    const state = setupCode();
    expect(state.screen).toMatchObject({
      step: "code",
      flow: "setup",
      value: "",
      dead: false,
      resendIn: 60,
      tries: 0,
    });
  });

  it("counts a second at a time down to zero", () => {
    let state = setupCode();
    for (let i = 0; i < 70; i++) state = reduce(state, { type: "resendTick" });
    expect(state.screen).toMatchObject({ resendIn: 0 });
  });

  it("clears a wrong code, counts the try, and kills the code after five", () => {
    let state = run(setupCode(), { type: "codeEdited", value: "000000" });
    state = reduce(state, { type: "codeWrong" });
    expect(state.screen).toMatchObject({
      value: "",
      tries: 1,
      dead: false,
      error: "That code is wrong. 4 tries left.",
    });
    for (let i = 0; i < 4; i++) state = reduce(state, { type: "codeWrong" });
    expect(state.screen).toMatchObject({
      dead: true,
      resendIn: 0,
      error: "Too many wrong codes. Tap Send a new code.",
    });
  });

  it("keeps a dead code's message when more is typed", () => {
    let state = setupCode();
    for (let i = 0; i < 5; i++) state = reduce(state, { type: "codeWrong" });
    state = reduce(state, { type: "codeEdited", value: "123" });
    expect(state.screen).toMatchObject({
      error: "Too many wrong codes. Tap Send a new code.",
    });
  });

  it("a new code starts the tries again", () => {
    let state = setupCode();
    for (let i = 0; i < 3; i++) state = reduce(state, { type: "codeWrong" });
    state = run(state, {
      type: "codeRequested",
      flow: "setup",
      lead: "",
      maskedEmail: "",
      developmentCode: "",
    });
    expect(state.screen).toMatchObject({ tries: 0, dead: false, resendIn: 60 });
  });

  it("turns a code the server refused at the end into a dead code step", () => {
    const state = run(confirming("5937"), {
      type: "codeDead",
      message: "This code no longer works. Tap Send a new code.",
    });
    expect(state.screen).toMatchObject({
      step: "code",
      flow: "setup",
      dead: true,
      resendIn: 0,
    });
    expect(JSON.stringify(state)).not.toContain("5937");
    expect(JSON.stringify(state)).not.toContain("918273");
  });

  it("a verified setup code opens the choose pad holding the code", () => {
    const state = run(setupCode(), { type: "codeVerified", code: "918273" });
    expect(pad(state)).toMatchObject({
      mode: "choose",
      flow: "setup",
      code: "918273",
    });
  });

  it("a verified sign-in code changes nothing here", () => {
    const state = signinCode("7319");
    expect(reduce(state, { type: "codeVerified", code: "918273" })).toBe(state);
  });
});

describe("secrets are dropped structurally", () => {
  it("cancelling the sign-in code step keeps no typed PIN", () => {
    const withCode = signinCode("7319");
    expect(JSON.stringify(withCode)).toContain("7319");
    const cancelled = reduce(withCode, { type: "codeCancelled" });
    expect(pad(cancelled)).toMatchObject({ mode: "enter", pin: "" });
    expect(JSON.stringify(cancelled)).not.toContain("7319");
  });

  it("cancelling on a trusted phone returns to the unlock pad", () => {
    const state = run(
      trusted(),
      {
        type: "codeRequested",
        flow: "reset",
        lead: "",
        maskedEmail: "",
        developmentCode: "",
      },
      { type: "codeCancelled" },
    );
    expect(pad(state)).toMatchObject({ mode: "unlock" });
  });

  it("cancelling a first-PIN code on an untrusted phone returns to the number step", () => {
    const state = reduce(setupCode(), { type: "codeCancelled" });
    expect(state.screen).toMatchObject({ step: "phone" });
  });

  it("forgetting the person from the confirm pad keeps neither the chosen PIN nor the code", () => {
    const withSecrets = confirming("5937", "918273");
    expect(JSON.stringify(withSecrets)).toContain("5937");
    expect(JSON.stringify(withSecrets)).toContain("918273");
    const forgotten = reduce(withSecrets, { type: "userForgotten" });
    expect(JSON.stringify(forgotten)).not.toContain("5937");
    expect(JSON.stringify(forgotten)).not.toContain("918273");
    expect(forgotten.person).toBeNull();
    expect(forgotten.phone).toBe("");
    expect(forgotten.screen).toMatchObject({ step: "phone" });
  });

  it("a finished sign-in keeps no secret", () => {
    const state = reduce(confirming("5937", "918273"), { type: "completed" });
    expect(JSON.stringify(state)).not.toContain("5937");
    expect(JSON.stringify(state)).not.toContain("918273");
  });

  it("asking for a reset code from the pad drops the typed PIN", () => {
    const state = run(typed(trusted(), "48"), {
      type: "codeRequested",
      flow: "reset",
      lead: "",
      maskedEmail: "",
      developmentCode: "",
    });
    expect(JSON.stringify(state)).not.toContain("48");
  });

  it("a profile that could not be loaded after a code returns to the pad without secrets", () => {
    const message = "Signed in, but your profile could not be loaded.";
    const fromSignin = reduce(signinCode("7319"), {
      type: "profileFailed",
      pinLength: 4,
      message,
    });
    expect(pad(fromSignin)).toMatchObject({
      mode: "enter",
      pin: "",
      error: message,
    });
    expect(JSON.stringify(fromSignin)).not.toContain("7319");

    const fromConfirm = reduce(confirming("5937", "918273"), {
      type: "profileFailed",
      pinLength: 4,
      message,
    });
    expect(pad(fromConfirm)).toMatchObject({
      mode: "enter",
      pin: "",
      error: message,
    });
    expect(JSON.stringify(fromConfirm)).not.toContain("5937");
    expect(JSON.stringify(fromConfirm)).not.toContain("918273");
  });

  it("a profile that could not be loaded returns to the unlock pad on a trusted phone, with the PIN length used", () => {
    const state = reduce(
      run(trusted(), {
        type: "codeRequested",
        flow: "reset",
        lead: "",
        maskedEmail: "",
        developmentCode: "",
      }),
      { type: "profileFailed", pinLength: 6, message: "x" },
    );
    expect(pad(state)).toMatchObject({ mode: "unlock" });
    expect(state.pinLength).toBe(6);
  });
});

describe("a pause", () => {
  it("counts the seconds left from the end time", () => {
    const state = run(
      trusted(),
      { type: "paused", until: 100_000, now: 40_000 },
      { type: "pauseTick", now: 70_000 },
    );
    expect(state.screen).toMatchObject({
      step: "paused",
      remaining: 30,
      until: 100_000,
    });
  });

  it("returns to the unlock pad on a trusted phone and the enter pad otherwise", () => {
    const ended = (state: AuthState) =>
      run(state, { type: "paused", until: 1, now: 0 }, { type: "pauseEnded" });
    expect(pad(ended(trusted()))).toMatchObject({
      mode: "unlock",
      pin: "",
      error: "",
    });
    const elsewhere = run(trusted(), {
      type: "phoneAccepted",
      phone: "0712345678",
    });
    expect(pad(ended(elsewhere)) as PadScreen).toMatchObject({ mode: "enter" });
  });

  it("drops the typed PIN when a pause begins", () => {
    const state = run(typed(trusted(), "48"), {
      type: "paused",
      until: 9,
      now: 0,
    });
    expect(JSON.stringify(state)).not.toContain("48");
  });
});

describe("signing out", () => {
  it("forgetting the person resets the number step", () => {
    const state = run(
      trusted(),
      { type: "phoneEdited", input: "0733 520 614" },
      { type: "userForgotten" },
    );
    expect(state).toMatchObject({
      person: null,
      phone: "",
      phoneInput: "",
      pinLength: 4,
    });
    expect(state.screen).toEqual({ step: "phone", fieldError: "", banner: "" });
  });

  it("an action that does not fit the screen changes nothing", () => {
    const state = trusted();
    expect(reduce(state, { type: "codeWrong" })).toBe(state);
    expect(reduce(state, { type: "resendTick" })).toBe(state);
    expect(reduce(state, { type: "pauseEnded" })).toBe(state);
  });
});
