// Time windows (days) offered for the candidate query.
export const WINDOWS = [3, 7, 14, 30, 90, 180, 365] as const;

// Target sizes for the smart-selection presets. 4-up slides render best at
// multiples of 4.
export const COUNTS = [4, 8, 12, 16] as const;

// Quick hook-text suggestions for the TikTok cover slide.
export const HOOK_PRESETS = [
  "WEEKLY ROTATION",
  "ELITE TASTE",
  "CURRENT REPEATS",
  "ON REPEAT",
];

export interface CoverTheme {
  value: string;
  label: string;
  emoji: string;
  // A representative gradient (Tailwind classes) for previewing the theme in
  // the UI. The actual slide gradient is rendered server-side.
  swatch: string;
}

export const COVER_THEMES: CoverTheme[] = [
  { value: "purple", label: "Royal Purple", emoji: "🟣", swatch: "from-violet-600 to-purple-700" },
  { value: "sunset", label: "Hot Pink Sunset", emoji: "🌸", swatch: "from-pink-500 to-rose-600" },
  { value: "sunrise", label: "Sunrise Orange", emoji: "🔥", swatch: "from-orange-500 to-red-600" },
  { value: "neon", label: "Neon Pink", emoji: "💖", swatch: "from-fuchsia-500 to-pink-600" },
  { value: "emerald", label: "Emerald Green", emoji: "🟢", swatch: "from-emerald-500 to-green-700" },
  { value: "royal", label: "Classic Blue", emoji: "🔵", swatch: "from-blue-600 to-indigo-700" },
  { value: "dark", label: "Charcoal Dark", emoji: "⚫", swatch: "from-zinc-700 to-zinc-900" },
];

// Compact label for a window length (e.g. 7 -> "7d", 90 -> "3mo", 365 -> "1yr").
export function windowLabel(days: number): string {
  if (days >= 365) return "1yr";
  if (days >= 90) return `${Math.round(days / 30)}mo`;
  return `${days}d`;
}

// Longer label for headers and the cover subtitle default.
export function windowLongLabel(days: number): string {
  if (days >= 365) return "Last 1 Year";
  if (days >= 90) return `Last ${Math.round(days / 30)} Months`;
  return `Last ${days} Days`;
}
