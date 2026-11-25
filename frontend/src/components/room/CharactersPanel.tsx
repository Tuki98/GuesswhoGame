import { ImagePlus, Search, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { AddCharacterDialog } from "@/components/room/AddCharacterDialog";
import { CharacterCard } from "@/components/room/CharacterCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Feedback";
import { Modal } from "@/components/ui/Modal";
import { Select, TextInput } from "@/components/ui/Field";
import { pluralize } from "@/lib/format";
import { useAuthStore } from "@/stores/authStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useRoomStore } from "@/stores/roomStore";
import {
  CATEGORY_LABELS,
  CHARACTER_CATEGORIES,
  type Character,
  type CharacterCategory,
} from "@/types/api";

export function CharactersPanel() {
  const session = useAuthStore((state) => state.session);
  const room = useRoomStore((state) => state.room);
  const players = useRoomStore((state) => state.players);
  const teams = useRoomStore((state) => state.teams);
  const characters = useRoomStore((state) => state.characters);
  const deleteCharacter = useRoomStore((state) => state.deleteCharacter);
  const connected = useConnectionStore((state) => state.status === "connected");
  const [addOpen, setAddOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Character | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<CharacterCategory | "all">("all");

  const contributorNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const player of players) {
      map.set(player.id, player.nickname);
    }
    return map;
  }, [players]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return characters.filter((character) => {
      if (category !== "all" && character.category !== category) {
        return false;
      }
      if (!needle) {
        return true;
      }
      return (
        character.name.toLowerCase().includes(needle) ||
        (character.franchise ?? "").toLowerCase().includes(needle)
      );
    });
  }, [characters, query, category]);

  if (!session || !room) {
    return null;
  }

  const waiting = room.status === "waiting";
  const isHost = room.host_player_id === session.playerId;
  const required = room.settings.game_mode === "team" ? teams.length : players.length;
  const needed = Math.max(0, required - characters.length);
  const canAdd = waiting && connected;

  async function onDelete() {
    if (!deleteTarget) {
      return;
    }
    setDeleting(true);
    const removed = await deleteCharacter(deleteTarget.id);
    setDeleting(false);
    if (removed) {
      setDeleteTarget(null);
    }
  }

  return (
    <>
      <Card className="p-5">
        <CardHeader
          title="Character collection"
          description="The shared pool used for secret assignments. Add enough for every player or team."
          action={
            <Button
              size="sm"
              onClick={() => setAddOpen(true)}
              disabled={!canAdd}
              icon={<ImagePlus className="h-4 w-4" />}
            >
              Add character
            </Button>
          }
        />

        <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={needed === 0 && characters.length > 0 ? "green" : "amber"}>
              {characters.length} {pluralize(characters.length, "character")}
            </Badge>
            <span className="text-xs text-slate-500">
              {room.settings.game_mode === "team"
                ? `At least ${Math.max(2, teams.length)} needed for ${teams.length} ${pluralize(
                    teams.length,
                    "team",
                  )}`
                : `At least ${players.length} needed for ${players.length} ${pluralize(
                    players.length,
                    "player",
                  )}`}
            </span>
            {needed > 0 ? (
              <Badge tone="amber">{needed} more recommended</Badge>
            ) : null}
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
                aria-hidden="true"
              />
              <TextInput
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search characters"
                aria-label="Search characters"
                className="h-9 pl-9 text-xs sm:w-52"
              />
            </div>
            <Select
              value={category}
              onChange={(event) =>
                setCategory(event.target.value as CharacterCategory | "all")
              }
              aria-label="Filter by category"
              className="h-9 py-1 text-xs sm:w-44"
            >
              <option value="all">All categories</option>
              {CHARACTER_CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {CATEGORY_LABELS[value]}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {!waiting ? (
          <p className="mt-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-slate-400">
            The collection is locked while a match is in progress.
          </p>
        ) : null}

        {characters.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              icon={<Sparkles className="h-6 w-6" />}
              title="The collection is empty"
              message={
                canAdd
                  ? "Add the first character with an image, a name, and a category."
                  : "The host needs to add characters before the match can start."
              }
              action={
                canAdd ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setAddOpen(true)}
                    icon={<ImagePlus className="h-4 w-4" />}
                  >
                    Add the first character
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : filtered.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              icon={<Search className="h-6 w-6" />}
              title="No matching characters"
              message="Try a different search term or category."
              action={
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setQuery("");
                    setCategory("all");
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          </div>
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((character) => {
              const canDelete =
                waiting &&
                connected &&
                (isHost || character.contributed_by === session.playerId);
              return (
                <CharacterCard
                  key={character.id}
                  character={character}
                  contributorName={
                    character.contributed_by
                      ? contributorNames.get(character.contributed_by) ?? null
                      : null
                  }
                  canDelete={canDelete}
                  onDelete={() => setDeleteTarget(character)}
                />
              );
            })}
          </div>
        )}
      </Card>

      <AddCharacterDialog open={addOpen} onClose={() => setAddOpen(false)} />

      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        title="Remove character?"
        description={
          deleteTarget
            ? `${deleteTarget.name} will be removed from this room's collection.`
            : undefined
        }
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="danger" loading={deleting} onClick={() => void onDelete()}>
              Remove character
            </Button>
          </>
        }
      >
        <p className="text-sm leading-6 text-slate-400">
          Characters can only be removed while the room is waiting. The host and
          the contributor can remove a character.
        </p>
      </Modal>
    </>
  );
}
