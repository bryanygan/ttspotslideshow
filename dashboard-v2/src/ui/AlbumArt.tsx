import { useRef, useState } from "react";
import type { Candidate } from "../lib/types";
import { resolveArt } from "../lib/api";
import { ImageIcon, MusicIcon } from "./icons";

interface AlbumArtProps {
  apiBase: string;
  track: Candidate;
  className?: string;
  rounded?: string;
  // When provided, tapping the art opens a file picker to replace the cover.
  onUpload?: (file: File) => void;
}

// Album art with a graceful music-note fallback and an optional
// tap-to-replace-cover affordance (used in the candidate browse views).
export function AlbumArt({
  apiBase,
  track,
  className = "h-12 w-12",
  rounded = "rounded-lg",
  onUpload,
}: AlbumArtProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [broken, setBroken] = useState(false);
  const src = resolveArt(apiBase, track.album_art_url);
  const editable = Boolean(onUpload);

  return (
    <div
      className={`group/art relative shrink-0 overflow-hidden bg-zinc-800 ${rounded} ${className} ${
        editable ? "cursor-pointer" : ""
      }`}
      onClick={
        editable
          ? (e) => {
              e.stopPropagation();
              inputRef.current?.click();
            }
          : undefined
      }
      title={editable ? "Replace cover art" : undefined}
    >
      {src && !broken ? (
        <img
          src={src}
          alt={track.title}
          loading="lazy"
          className="h-full w-full object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-zinc-600">
          <MusicIcon className="h-1/3 w-1/3" />
        </div>
      )}

      {editable && (
        <>
          <div className="absolute inset-0 flex items-center justify-center bg-black/60 text-white opacity-0 transition-opacity group-hover/art:opacity-100">
            <ImageIcon className="h-1/3 w-1/3" />
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file && onUpload) onUpload(file);
              e.target.value = "";
            }}
          />
        </>
      )}
    </div>
  );
}
