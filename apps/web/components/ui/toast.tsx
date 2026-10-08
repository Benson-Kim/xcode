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

// Short confirmations after a save (.toast), shown along the bottom of the screen for four seconds.
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const show = useCallback((message: string) => {
    setToasts((current) => [
      ...current,
      { id: Date.now() + Math.random(), message },
    ]);
  }, []);
  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="pointer-events-none fixed bottom-6 left-1/2 z-60 flex w-max max-w-[calc(100%-32px)] -translate-x-1/2 flex-col items-center gap-2">
        {toasts.map((toast) => (
          <ToastMessage
            key={toast.id}
            id={toast.id}
            message={toast.message}
            onDone={dismiss}
          />
        ))}
      </div>
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
    <div
      role="status"
      className="rounded-xl bg-brand px-4.5 py-3 text-[15px] text-white shadow-toast"
    >
      {message}
    </div>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
