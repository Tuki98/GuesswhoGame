import { create } from "zustand";

import { api } from "@/api/endpoints";
import { withAuth } from "@/api/authorized";
import { errorMessage } from "@/lib/errors";
import { dispatchSocketAction } from "@/realtime/actions";
import { realtime } from "@/realtime/realtime";
import { usePendingStore } from "@/stores/pendingStore";
import { toastError } from "@/stores/uiStore";
import type { GameEvent, MatchState } from "@/types/api";

interface MatchStore {
  state: MatchState | null;
  history: GameEvent[];
  lastSequence: number | null;
  historyHasMore: boolean;
  syncing: boolean;
  error: string | null;
  endedReason: string | null;
  setState: (state: MatchState) => void;
  loadState: (matchId: string) => Promise<boolean>;
  syncHistory: (matchId?: string, afterSequence?: number | null) => Promise<void>;
  startMatch: () => string | null;
  sendQuestion: (content: string, recipientId: string) => string | null;
  sendAnswer: (content: string, questionId: string) => string | null;
  submitGuess: (characterId: string) => string | null;
  cancelMatch: () => string | null;
  requestState: (delayMs?: number) => void;
  setEndedReason: (reason: string | null) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

let historyVersion = 0;
let stateRequestTimer: ReturnType<typeof setTimeout> | null = null;
const MAX_HISTORY_PAGES = 20;

export function mergeEvents(existing: GameEvent[], incoming: GameEvent[]): GameEvent[] {
  const bySequence = new Map<number, GameEvent>();
  for (const event of existing) {
    bySequence.set(event.sequence_number, event);
  }
  for (const event of incoming) {
    bySequence.set(event.sequence_number, event);
  }
  return [...bySequence.values()].sort((left, right) => {
    if (left.sequence_number !== right.sequence_number) {
      return left.sequence_number - right.sequence_number;
    }
    return new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
  });
}

function clearStateRequestTimer(): void {
  if (stateRequestTimer) {
    clearTimeout(stateRequestTimer);
    stateRequestTimer = null;
  }
}

export const useMatchStore = create<MatchStore>()((set, get) => ({
  state: null,
  history: [],
  lastSequence: null,
  historyHasMore: false,
  syncing: false,
  error: null,
  endedReason: null,

  setState: (next) => {
    const current = get().state;
    if (current && current.match.id !== next.match.id) {
      historyVersion += 1;
      set({
        state: next,
        history: [],
        lastSequence: null,
        historyHasMore: false,
        endedReason: null,
        error: null,
      });
      return;
    }
    set({ state: next, error: null });
  },

  loadState: async (matchId) => {
    try {
      const state = await withAuth((token) => api.getMatchState(matchId, token));
      get().setState(state);
      return true;
    } catch (error) {
      set({ error: errorMessage(error) });
      return false;
    }
  },

  syncHistory: async (matchId, afterSequence) => {
    const targetMatchId = matchId ?? get().state?.match.id;
    if (!targetMatchId) {
      return;
    }
    const sameMatch = get().state?.match.id === targetMatchId;
    const startAfter =
      afterSequence !== undefined
        ? afterSequence
        : sameMatch
          ? get().lastSequence
          : null;
    const version = ++historyVersion;
    set({ syncing: true });
    let after = startAfter;
    let merged = sameMatch ? get().history : [];
    let hasMore = false;

    try {
      for (let page = 0; page < MAX_HISTORY_PAGES; page += 1) {
        const response = await withAuth((token) =>
          api.getMatchHistory(targetMatchId, token, {
            limit: 100,
            afterSequence: after,
          }),
        );
        if (version !== historyVersion) {
          return;
        }
        merged = mergeEvents(merged, response.events);
        const lastEvent = response.events.at(-1);
        if (lastEvent) {
          after = Math.max(after ?? 0, lastEvent.sequence_number);
        }
        hasMore = response.has_more;
        if (!response.has_more) {
          break;
        }
        if (response.next_after_sequence === null && !lastEvent) {
          break;
        }
        if (response.next_after_sequence !== null) {
          after = response.next_after_sequence;
        }
      }
      if (version !== historyVersion) {
        return;
      }
      const lastSequence = merged.at(-1)?.sequence_number ?? startAfter ?? null;
      set({
        history: merged,
        lastSequence,
        historyHasMore: hasMore,
        syncing: false,
        error: null,
      });
    } catch (error) {
      if (version !== historyVersion) {
        return;
      }
      set({ syncing: false, error: errorMessage(error) });
    }
  },

  startMatch: () => {
    return dispatchSocketAction(
      "match.start",
      {},
      { key: "match_start", label: "Starting the match" },
    );
  },

  sendQuestion: (content, recipientId) => {
    const state = get().state;
    if (!state) {
      return null;
    }
    const trimmed = content.trim();
    if (!trimmed || trimmed.length > 500) {
      toastError("Question not sent", "Questions must be between 1 and 500 characters.");
      return null;
    }
    const payload: Record<string, unknown> = { content: trimmed };
    if (state.match.mode === "team") {
      payload.recipient_team_id = recipientId;
    } else {
      payload.recipient_player_id = recipientId;
    }
    const requestId = dispatchSocketAction("question.submit", payload, {
      key: "question",
      label: "Sending your question",
    });
    if (requestId) {
      // The protocol has no direct ack for question.submit. The server processes
      // messages in order, so an immediate personalized state request is the
      // authoritative way to reconcile the pending question.
      get().requestState(0);
      window.setTimeout(() => usePendingStore.getState().finish("question"), 1_600);
    }
    return requestId;
  },

  sendAnswer: (content, questionId) => {
    const trimmed = content.trim();
    if (!trimmed || trimmed.length > 1_000) {
      toastError("Answer not sent", "Answers must be between 1 and 1000 characters.");
      return null;
    }
    return dispatchSocketAction(
      "answer.submit",
      { content: trimmed, question_id: questionId },
      { key: "answer", label: "Sending your answer" },
    );
  },

  submitGuess: (characterId) => {
    return dispatchSocketAction(
      "guess.submit",
      { character_id: characterId },
      { key: "guess", label: "Submitting your guess" },
    );
  },

  cancelMatch: () => {
    return dispatchSocketAction(
      "match.cancel",
      {},
      { key: "match_cancel", label: "Cancelling the match" },
    );
  },

  requestState: (delayMs = 120) => {
    clearStateRequestTimer();
    stateRequestTimer = setTimeout(() => {
      stateRequestTimer = null;
      if (realtime.isOpen) {
        realtime.send("match.get_state", {});
      }
    }, delayMs);
  },

  setError: (error) => set({ error }),

  setEndedReason: (reason) => set({ endedReason: reason }),

  reset: () => {
    clearStateRequestTimer();
    historyVersion += 1;
    set({
      state: null,
      history: [],
      lastSequence: null,
      historyHasMore: false,
      syncing: false,
      endedReason: null,
      error: null,
    });
  },
}));
