import { describe, expect, it } from "vitest";

import {
  formatPhone,
  initials,
  maskPhone,
  normalisePhone,
  phoneError,
} from "@xcode/shared/format";

describe("phone numbers", () => {
  it.each([
    ["", ""],
    ["abc", ""],
    ["254711000001", "0711000001"],
    ["+254 111 000 001", "0111000001"],
    ["711000001", "0711000001"],
    ["1234", "01234"],
    ["811000001", "811000001"],
  ])("normalises %j to %j", (value, expected) => {
    expect(normalisePhone(value)).toBe(expected);
  });

  it.each([
    ["0711000001", "0711 000 001"],
    ["+254711000001", "0711 000 001"],
    ["0711", "0711"],
    ["07110000012", "07110000012"],
  ])("formats %j as %j", (value, expected) => {
    expect(formatPhone(value)).toBe(expected);
  });

  it.each([
    ["0711000001", "0711 ••• 001"],
    ["+254 711 000 001", "0711 ••• 001"],
    ["711000001", "0711 ••• 001"],
    ["0111000001", "0111 ••• 001"],
    ["0711 000 0012", "0711 000 0012"],
    ["", ""],
    ["abc", "abc"],
  ])("masks %j as %j", (value, expected) => {
    expect(maskPhone(value)).toBe(expected);
  });

  it.each([
    ["", "Enter your mobile number."],
    ["abc", "Enter your mobile number."],
    ["0211000001", "Enter all 10 numbers, starting 07 or 01."],
    ["0711", "Enter all 10 numbers, starting 07 or 01."],
    ["0111000001", ""],
    ["+254 711 000 001", ""],
  ])("checks %j: %j", (value, expected) => {
    expect(phoneError(value)).toBe(expected);
  });
});

describe("initials", () => {
  it.each([
    ["Jane", "Doe", "JD"],
    ["jane", "doe", "JD"],
    ["", "Doe", "D"],
    ["Jane", "", "J"],
    ["", "", ""],
    ["élan", "ñu", "ÉÑ"],
  ])("of %j %j are %j", (first, last, expected) => {
    expect(initials(first, last)).toBe(expected);
  });
});
