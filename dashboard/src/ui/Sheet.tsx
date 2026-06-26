import { useEffect } from "react";
import type { ReactNode } from "react";
import { CloseIcon } from "./icons";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  // Panel styling so each option can theme the sheet to its own identity.
  panelClass?: string;
}

// A bottom sheet that slides up on mobile and on desktop. Closes on backdrop
// click and Escape; locks body scroll while open.
export function Sheet({ open, onClose, title, children, panelClass = "" }: SheetProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        className={`relative flex max-h-[88vh] w-full flex-col overflow-hidden shadow-2xl sm:max-w-lg ${panelClass}`}
      >
        {title && (
          <div className="flex items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
            <div className="min-w-0 text-base font-semibold">{title}</div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-full p-1.5 text-zinc-400 transition-colors hover:bg-white/10 hover:text-white"
            >
              <CloseIcon className="h-5 w-5" />
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4 pb-safe">
          {children}
        </div>
      </div>
    </div>
  );
}
