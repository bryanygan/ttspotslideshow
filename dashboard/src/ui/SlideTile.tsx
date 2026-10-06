import { useState } from "react";
import { slideDownloadUrl, slidePreviewUrl, slideThumbUrl } from "../lib/slides";

// Lightweight WebP preview of a slide. `src` is the slide's full PNG URL;
// if the WebP copies can't load, it falls back to the PNG itself.
export function SlideThumb({
  src,
  alt,
  sizes = "(min-width: 640px) 33vw, 50vw",
  className = "",
}: {
  src: string;
  alt: string;
  sizes?: string;
  className?: string;
}) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const failed = failedSrc === src;
  const thumb = slideThumbUrl(src);
  const preview = slidePreviewUrl(src);

  return (
    <img
      src={failed ? src : thumb}
      srcSet={failed ? undefined : `${thumb} 540w, ${preview} 1080w`}
      sizes={sizes}
      alt={alt}
      loading="lazy"
      decoding="async"
      width={1080}
      height={1700}
      onError={() => setFailedSrc(src)}
      className={`h-auto w-full ${className}`}
    />
  );
}

// Grid tile: tap opens the full HD PNG; the button below downloads it.
export function SlideTile({ src, index }: { src: string; index: number }) {
  return (
    <div className="flex flex-col gap-1.5">
      <a href={src} target="_blank" rel="noopener noreferrer" className="group block">
        <SlideThumb
          src={src}
          alt={`Slide ${index + 1}`}
          className="rounded-xl border border-zinc-800 transition-colors group-hover:border-violet-500/60"
        />
      </a>
      <div className="flex items-center justify-between gap-2 px-0.5">
        <span className="text-[11px] font-medium text-zinc-500">Slide {index + 1}</span>
        <a
          href={slideDownloadUrl(src)}
          download
          className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[11px] font-semibold text-zinc-300 transition-colors hover:border-violet-500/60 hover:text-violet-200"
        >
          ⬇ HD PNG
        </a>
      </div>
    </div>
  );
}
