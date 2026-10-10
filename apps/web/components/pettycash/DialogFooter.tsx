import type { ReactNode } from "react";

import { FormActions } from "../ui";

export function DialogFooter({ children }: { children: ReactNode }) {
  return (
    <FormActions className="-mx-[22px] -mb-5 justify-end gap-2.5 border-t border-line bg-paper px-[22px] py-3.5 max-[600px]:[&_button]:flex-1 [&_button]:min-w-27">
      {children}
    </FormActions>
  );
}
