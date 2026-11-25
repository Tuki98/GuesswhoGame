import { Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/cn";

export function Brand({
  compact = false,
  link = true,
}: {
  compact?: boolean;
  link?: boolean;
}) {
  const content = (
    <span className="inline-flex items-center gap-2.5">
      <span className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-violet-400/25 bg-gradient-to-br from-violet-500/30 to-cyan-400/10 shadow-glow">
        <Sparkles className="h-5 w-5 text-violet-200" aria-hidden="true" />
      </span>
      <span className={cn("font-display font-semibold tracking-tight text-white", compact ? "text-base" : "text-lg")}>
        Guess the Character
      </span>
    </span>
  );
  return link ? (
    <Link
      to="/"
      className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
      aria-label="Guess the Character home"
    >
      {content}
    </Link>
  ) : (
    content
  );
}
