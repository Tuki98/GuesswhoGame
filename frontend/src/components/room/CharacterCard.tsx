import { Trash2 } from "lucide-react";

import { CharacterImage } from "@/components/room/CharacterImage";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CATEGORY_LABELS, type Character } from "@/types/api";

export function CharacterCard({
  character,
  contributorName,
  canDelete,
  onDelete,
}: {
  character: Character;
  contributorName: string | null;
  canDelete: boolean;
  onDelete: () => void;
}) {
  return (
    <div className="group overflow-hidden rounded-xl border border-white/10 bg-black/20 transition hover:border-white/20 hover:bg-white/[0.04]">
      <div className="relative aspect-[4/3] overflow-hidden">
        <CharacterImage
          name={character.name}
          imageUrl={character.image_url}
          rounded="rounded-none"
          className="h-full w-full transition duration-300 group-hover:scale-[1.03]"
        />
        <span className="absolute left-2 top-2">
          <Badge tone="violet" className="backdrop-blur">
            {CATEGORY_LABELS[character.category]}
          </Badge>
        </span>
      </div>
      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate font-display text-sm font-semibold text-white" title={character.name}>
              {character.name}
            </h3>
            <p className="truncate text-xs text-slate-500" title={character.franchise ?? undefined}>
              {character.franchise || "Unknown franchise"}
            </p>
          </div>
          {canDelete ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={onDelete}
              aria-label={`Remove ${character.name}`}
              title={`Remove ${character.name}`}
              className="h-8 w-8 shrink-0 px-0 text-slate-500 hover:bg-rose-500/10 hover:text-rose-300"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
        {contributorName ? (
          <p className="mt-1 truncate text-[11px] text-slate-600">
            Added by {contributorName}
          </p>
        ) : null}
      </div>
    </div>
  );
}
