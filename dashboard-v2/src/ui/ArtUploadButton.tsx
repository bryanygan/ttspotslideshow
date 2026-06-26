import { useRef } from "react";
import { ImageIcon } from "./icons";

// A self-contained "replace cover" button with its own hidden file input, so it
// can sit on a card whose body handles selection without click conflicts.
export function ArtUploadButton({
  onFile,
  className = "",
}: {
  onFile: (file: File) => void;
  className?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <button
        type="button"
        aria-label="Replace cover art"
        title="Replace cover art"
        onClick={(e) => {
          e.stopPropagation();
          inputRef.current?.click();
        }}
        className={className}
      >
        <ImageIcon className="h-4 w-4" />
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </>
  );
}
