import { createContext, useContext } from "react";

// v2.38: false while the owner has Targets switched off, read from the appearance. Every target and gap figure is
// then hidden; the low revenue figure and the fuel question stay.
export const TargetsContext = createContext(true);

export const useTargets = () => useContext(TargetsContext);
