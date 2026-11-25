import { Eye, Users } from "lucide-react";

import { CharacterImage } from "@/components/room/CharacterImage";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Feedback";
import { CATEGORY_LABELS, type VisibleCharacter } from "@/types/api";

function formatAttribute(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "—";
  }
}

export function OpponentsPanel({ opponents }: { opponents: VisibleCharacter[] }) {
  const groups = new Map<
    string,
    { ownerId: string; ownerName: string; ownerKind: "player" | "team"; items: VisibleCharacter[] }
  >();

  for (const entry of opponents) {
    const existing = groups.get(entry.owner_id);
    if (existing) {
      existing.items.push(entry);
    } else {
      groups.set(entry.owner_id, {
        ownerId: entry.owner_id,
        ownerName: entry.owner_name,
        ownerKind: entry.owner_kind,
        items: [entry],
      });
    }
  }

  return (
    <Card className="p-5">
      <CardHeader
        title="Characters you can see"
        description="Every other participant's secret is visible to you. Yours is not shown anywhere."
        action={<Eye className="h-5 w-5 text-slate-500" aria-hidden="true" />}
      />

      {opponents.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            icon={<Users className="h-6 w-6" />}
            title="No revealed characters yet"
            message="The table will fill in as soon as assignments are delivered to this connection."
          />
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {[...groups.values()].map((group) => (
            <div
              key={group.ownerId}
              className="rounded-xl border border-white/10 bg-black/20 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Avatar
                  name={group.ownerName}
                  size="sm"
                />
                <span className="text-sm font-semibold text-white">{group.ownerName}</span>
                {group.ownerKind === "team" ? (
                  <Badge tone="cyan">
                    <Users className="h-3 w-3" aria-hidden="true" />
                    Team
                  </Badge>
                ) : (
                  <Badge tone="neutral">Player</Badge>
                )}
                <span className="ml-auto text-xs text-slate-500">
                  {group.items.length === 1 ? "1 character" : `${group.items.length} characters`}
                </span>
              </div>

              <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
                {group.items.map((entry) => (
                  <div
                    key={`${entry.owner_id}-${entry.character.id}`}
                    className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-2"
                  >
                    <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg">
                      <CharacterImage
                        name={entry.character.name}
                        imageUrl={entry.character.image_url}
                        className="h-full w-full"
                      />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-display text-sm font-semibold text-white">
                        {entry.character.name}
                      </p>
                      <p className="truncate text-xs text-slate-500">
                        {entry.character.franchise || CATEGORY_LABELS[entry.character.category]}
                      </p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {Object.entries(entry.character.attributes)
                          .slice(0, 2)
                          .map(([key, value]) => (
                            <span
                              key={key}
                              className="max-w-full truncate rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-slate-400"
                              title={`${key}: ${formatAttribute(value)}`}
                            >
                              {key}: {formatAttribute(value)}
                            </span>
                          ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
