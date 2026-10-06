// Slides are stored as a full-quality PNG plus WebP copies the server derives
// from it: <name>.webp (full size, q95) and <name>.thumb.webp (540px wide).
const PNG = /\.png$/i;

export const slidePreviewUrl = (url: string): string => url.replace(PNG, ".webp");
export const slideThumbUrl = (url: string): string => url.replace(PNG, ".thumb.webp");
export const slideDownloadUrl = (url: string): string =>
  `${url}${url.includes("?") ? "&" : "?"}download=1`;
