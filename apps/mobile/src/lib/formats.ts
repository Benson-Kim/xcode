import { createContext, useContext } from "react";

import { createFormatter, type Formatter } from "@xcode/shared/format";

export const FormatsContext = createContext<Formatter>(createFormatter());

export const useFormats = () => useContext(FormatsContext);
