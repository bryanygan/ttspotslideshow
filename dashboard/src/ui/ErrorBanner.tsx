import { AlertIcon } from "./icons";

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-rose-900/60 bg-rose-950/40 p-4 text-sm text-rose-200">
      <AlertIcon className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
      <div>{message}</div>
    </div>
  );
}
