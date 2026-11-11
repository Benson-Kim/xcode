"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

type Toast = { id: number; message: string };
const ToastContext = createContext<(message: string) => void>(() => {});

// Short confirmations after a save (.toast): one deep pill at the bottom centre for four seconds. A new message
// takes the place of the one showing, as in the design. While a pop up is open the pill is drawn inside it: a modal
// dialog sits in the top layer, above anything else on the page, and makes the rest inert.
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const show = useCallback((message: string) => {
    setToast({ id: Date.now() + Math.random(), message });
  }, []);
  const dismiss = useCallback((id: number) => {
    setToast((current) => (current?.id === id ? null : current));
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <ToastMessage
          key={toast.id}
          id={toast.id}
          message={toast.message}
          onDone={dismiss}
        />
      )}
    </ToastContext.Provider>
  );
}

function ToastMessage({
  id,
  message,
  onDone,
}: {
  id: number;
  message: string;
  onDone: (id: number) => void;
}) {
  const [host, setHost] = useState<HTMLDialogElement | null>(null);
  useEffect(() => {
    // A frame later, a pop up that closed with this message is gone.
    const frame = requestAnimationFrame(() => {
      const open = document.querySelectorAll<HTMLDialogElement>("dialog[open]");
      setHost(open[open.length - 1] ?? null);
    });
    const timer = setTimeout(() => onDone(id), 4000);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
    };
  }, [id, onDone]);
  const pill = (
    <div role="status" className="toast pointer-events-none">
      {message}
    </div>
  );
  return host ? createPortal(pill, host) : pill;
}

export function useToast() {
  return useContext(ToastContext);
}
