import { fireEvent, waitFor, within } from "@testing-library/react";

// The listbox a SearchSelect input controls.
export const listboxOf = (input: HTMLElement) =>
  document.getElementById(input.getAttribute("aria-controls") ?? "")!;

// Opens a SearchSelect and takes the option with this name, as a click or a tap does.
export function pick(input: HTMLElement, option: string | RegExp) {
  fireEvent.focus(input);
  fireEvent.click(
    within(listboxOf(input)).getByRole("option", { name: option }),
  );
}

// An option's name as assistive technology reads it: its text without the parts hidden from it, such as the group.
function nameOf(option: HTMLElement) {
  const copy = option.cloneNode(true) as HTMLElement;
  copy
    .querySelectorAll('[aria-hidden="true"]')
    .forEach((hidden) => hidden.remove());
  return copy.textContent;
}

// The names of the options a SearchSelect offers, after opening it.
export function optionsOf(input: HTMLElement) {
  fireEvent.focus(input);
  return within(listboxOf(input)).getAllByRole("option").map(nameOf);
}

// Takes the option with this text in a native select, as choosing it does.
export function choose(select: HTMLElement, option: string) {
  const found = Array.from((select as HTMLSelectElement).options).find(
    (candidate) => candidate.textContent === option,
  );
  if (!found) throw new Error(`The select offers no option "${option}".`);
  fireEvent.change(select, { target: { value: found.value } });
}

// Waits until a SearchSelect offers an option, as it does once the choices it was given have loaded.
export const offered = (input: HTMLElement, name: string | RegExp) =>
  waitFor(() => {
    fireEvent.focus(input);
    within(listboxOf(input)).getByRole("option", { name });
  });
