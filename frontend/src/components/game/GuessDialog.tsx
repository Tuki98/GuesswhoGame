import { Search, Sparkles, TriangleAlert, Trophy } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { CharacterImage } from "@/components/room/CharacterImage";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { useConnectionStore } from "@/stores/connectionStore";
import { useMatchStore } from "@/stores/matchStore";
import { usePendingStore } from "@/stores/pendingStore";
import { useRoomStore } from "@/stores/roomStore";
import { CATEGORY_LABELS, type Character, type MatchState } from "@/types/api";

export function GuessDialog({
  open,
  onClose,
  state,
}: {
  open: boolean;
  onClose: () => void;
  state: MatchState;
}) {
  const characters = useRoomStore((store) => store.characters);
  const teams = useRoomStore((store) => store.teams);
  const refreshCharacters = useRoomStore((store) => store.refreshCharacters);
  const submitGuess = useMatchStore((store) => store.submitGuess);
  const connected = useConnectionStore((store) => store.status === "connected");
  const guessing = usePendingStore((store) => Boolean(store.pending.guess));
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showRuledOut, setShowRuledOut] = useState(false);

  useEffect(() => {
    if (open && characters.length === 0) {
      void refreshCharacters();
    }
  }, [open, characters.length, refreshCharacters]);

  useEffect(() => {
    if (!open) {
      setSelected(null);
      setQuery("");
    }
  }, [open]);

  const ownContributorIds = useMemo(() => {
    if (state.match.mode !== "team" || !state.self.team_id) {
      return new Set([state.self.player_id]);
    }
    const ownTeam = teams.find((team) => team.id === state.self.team_id);
    const ids = ownTeam?.members.map((member) => member.id) ?? [];
    if (!ids.includes(state.self.player_id)) {
      ids.push(state.self.player_id);
    }
    return new Set(ids);
  }, [state.match.mode, state.self.team_id, state.self.player_id, teams]);

  const ruledOut = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of state.opponents) {
      map.set(entry.character.id, `Visible as ${entry.owner_name}'s character`);
    }
    for (const character of characters) {
      if (
        character.contributed_by &&
        ownContributorIds.has(character.contributed_by) &&
        !map.has(character.id)
      ) {
        map.set(
          character.id,
          state.match.mode === "team"
            ? "Contributed by your team"
            : "You contributed this character",
        );
      }
    }
    return map;
  }, [state.opponents, characters, ownContributorIds, state.match.mode]);

  const candidates = useMemo(
    () => characters.filter((character) => !ruledOut.has(character.id)),
    [characters, ruledOut],
  );

  const ruledOutCharacters = useMemo(
    () => characters.filter((character) => ruledOut.has(character.id)),
    [characters, ruledOut],
  );

  const filteredCandidates = filterCharacters(candidates, query);
  const filteredRuledOut = filterCharacters(ruledOutCharacters, query);
  const selectedCharacter = characters.find((character) => character.id === selected) ?? null;

  function close() {
    if (guessing) {
      return;
    }
    onClose();
  }

  function confirm() {
    if (!selected) {
      return;
    }
    const sent = submitGuess(selected);
    if (sent) {
      onClose();
    }
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="Guess your character"
      description="Pick the identity you believe is yours. The server checks it against your secret assignment."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={guessing}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={guessing}
            disabled={!connected || !selected}
            onClick={confirm}
            icon={<Trophy className="h-4 w-4" />}
          >
            Submit guess
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex items-start gap-2 rounded-xl border border-amber-400/20 bg-amber-500/[0.06] px-3 py-2.5 text-xs leading-5 text-amber-200">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          A correct guess wins the match immediately. An incorrect guess is
          recorded for everyone — but does not end your turn.
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="green">{candidates.length} possible</Badge>
            <Badge tone="neutral">{ruledOutCharacters.length} ruled out</Badge>
          </div>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
              aria-hidden="true"
            />
            <TextInput
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search the collection"
              aria-label="Search candidate characters"
              className="h-9 pl-9 text-xs sm:w-60"
            />
          </div>
        </div>

        {characters.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 px-4 py-8 text-center">
            <Sparkles className="mx-auto h-6 w-6 text-slate-500" aria-hidden="true" />
            <p className="mt-2 text-sm font-medium text-slate-300">
              Characters are not loaded yet
            </p>
            <p className="mt-1 text-xs text-slate-500">
              The collection is downloading. Try again in a moment.
            </p>
            <Button
              size="sm"
              variant="secondary"
              className="mt-3"
              onClick={() => void refreshCharacters()}
            >
              Refresh
            </Button>
          </div>
        ) : filteredCandidates.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 px-4 py-8 text-center">
            <p className="text-sm font-medium text-slate-300">
              {query ? "No candidates match that search" : "No candidates left"}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {query
                ? "Clear the search to see every remaining possibility."
                : "The server view is inconsistent with the local collection. Refresh the room."}
            </p>
          </div>
        ) : (
          <div className="grid max-h-[38vh] grid-cols-2 gap-2 overflow-y-auto pr-1 sm:grid-cols-3">
            {filteredCandidates.map((character) => (
              <CandidateCard
                key={character.id}
                character={character}
                selected={selected === character.id}
                onSelect={() => setSelected(character.id)}
              />
            ))}
          </div>
        )}

        {ruledOutCharacters.length > 0 ? (
          <div className="border-t border-white/10 pt-3">
            <button
              type="button"
              onClick={() => setShowRuledOut((current) => !current)}
              className="flex w-full items-center justify-between rounded-lg px-1 py-1.5 text-left text-xs font-medium text-slate-400 transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
              aria-expanded={showRuledOut}
            >
              <span>Ruled out by what you can already see</span>
              <span>{showRuledOut ? "Hide" : "Show"}</span>
            </button>
            {showRuledOut ? (
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {filteredRuledOut.map((character) => (
                  <div
                    key={character.id}
                    className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.02] p-2 opacity-70"
                  >
                    <div className="h-12 w-12 shrink-0 overflow-hidden rounded-md">
                      <CharacterImage
                        name={character.name}
                        imageUrl={character.image_url}
                        className="h-full w-full"
                      />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold text-slate-300">
                        {character.name}
                      </p>
                      <p className="truncate text-[11px] text-slate-500">
                        {ruledOut.get(character.id)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {selectedCharacter ? (
          <p className="rounded-lg border border-rose-400/20 bg-rose-500/[0.06] px-3 py-2 text-xs text-rose-200">
            Your guess: <span className="font-semibold">{selectedCharacter.name}</span>
            {selectedCharacter.franchise ? ` · ${selectedCharacter.franchise}` : ""}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}

function CandidateCard({
  character,
  selected,
  onSelect,
}: {
  character: Character;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`overflow-hidden rounded-xl border text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 ${
        selected
          ? "border-rose-400/60 bg-rose-500/10 ring-1 ring-rose-400/30"
          : "border-white/10 bg-black/20 hover:border-white/25 hover:bg-white/[0.04]"
      }`}
    >
      <div className="aspect-[4/3] overflow-hidden">
        <CharacterImage
          name={character.name}
          imageUrl={character.image_url}
          rounded="rounded-none"
          className="h-full w-full"
        />
      </div>
      <div className="p-2">
        <p className="truncate text-xs font-semibold text-white">{character.name}</p>
        <p className="truncate text-[11px] text-slate-500">
          {character.franchise || CATEGORY_LABELS[character.category]}
        </p>
      </div>
    </button>
  );
}

function filterCharacters(characters: Character[], query: string): Character[] {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return characters;
  }
  return characters.filter(
    (character) =>
      character.name.toLowerCase().includes(needle) ||
      (character.franchise ?? "").toLowerCase().includes(needle),
  );
}
