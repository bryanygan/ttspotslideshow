import { useState } from "react";

// Copy-to-clipboard with a fallback for non-secure contexts (e.g. http:// over
// LAN on a phone, where navigator.clipboard is unavailable). Shared by the
// recap gallery and the bi-daily captions.
export function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);

  async function copy() {
    if (!text) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (!ok) throw new Error("copy command failed");
      }
      setFailed(false);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setFailed(true);
      setTimeout(() => setFailed(false), 4000);
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={failed ? "Auto-copy blocked — long-press the text to copy" : "Copy"}
      className={
        className ??
        "rounded-lg border border-violet-700/60 bg-violet-900/40 px-2.5 py-1.5 text-[11px] font-semibold text-violet-300 transition-colors hover:bg-violet-800/60"
      }
    >
      {copied ? "Copied!" : failed ? "Long-press ↓" : "Copy"}
    </button>
  );
}
