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

// The names of the options a SearchSelect offers, after opening it.
export function optionsOf(input: HTMLElement) {
  fireEvent.focus(input);
  return within(listboxOf(input))
    .getAllByRole("option")
    .map((option) => option.textContent);
}

// Waits until a SearchSelect offers an option, as it does once the choices it was given have loaded.
export const offered = (input: HTMLElement, name: string | RegExp) =>
  waitFor(() => {
    fireEvent.focus(input);
    within(listboxOf(input)).getByRole("option", { name });
  });
