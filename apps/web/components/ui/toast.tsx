"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

type Toast = { id: number; message: string };
const ToastContext = createContext<(message: string) => void>(() => {});

// Short confirmations after a save (.toast): one deep pill at the bottom centre for four seconds. A new message
// takes the place of the one showing, as in the design.
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
  useEffect(() => {
    const timer = setTimeout(() => onDone(id), 4000);
    return () => clearTimeout(timer);
  }, [id, onDone]);
  return (
    <div role="status" className="toast">
      {message}
    </div>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
