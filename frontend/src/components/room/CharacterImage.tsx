import { ImageOff } from "lucide-react";
import { useState } from "react";

import { mediaUrl } from "@/api/client";
import { cn } from "@/lib/cn";

export function CharacterImage({
  name,
  imageUrl,
  className,
  rounded = "rounded-xl",
}: {
  name: string;
  imageUrl: string | null | undefined;
  className?: string;
  rounded?: string;
}) {
  const [failed, setFailed] = useState(false);
  const resolved = mediaUrl(imageUrl);
  const base = cn(
    "relative overflow-hidden border border-white/10 bg-black/30",
    rounded,
    className,
  );

  if (!resolved || failed) {
    return (
      <div className={cn(base, "flex h-full w-full items-center justify-center")} role="img" aria-label={name}>
        <div className="flex flex-col items-center gap-1.5 text-slate-600">
          <ImageOff className="h-6 w-6" aria-hidden="true" />
          <span className="px-2 text-center text-[10px] font-medium uppercase tracking-wide">
            No image
          </span>
        </div>
      </div>
    );
  }

  return (
    <img
      src={resolved}
      alt={name}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={cn(base, "h-full w-full object-cover")}
    />
  );
}
