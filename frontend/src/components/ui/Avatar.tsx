import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";

export function Avatar({
  name,
  size = "md",
  className,
}: {
  name: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const sizes = {
    sm: "h-8 w-8 text-xs",
    md: "h-10 w-10 text-sm",
    lg: "h-14 w-14 text-lg",
  };
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full border border-violet-400/20 bg-gradient-to-br from-violet-500/25 to-cyan-500/15 font-display font-semibold text-violet-100",
        sizes[size],
        className,
      )}
    >
      {initials(name) || "?"}
    </span>
  );
}
