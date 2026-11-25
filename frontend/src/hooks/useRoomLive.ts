import { useEffect, useRef } from "react";

import { realtime } from "@/realtime/realtime";
import { useAuthStore } from "@/stores/authStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useMatchStore } from "@/stores/matchStore";
import { usePendingStore } from "@/stores/pendingStore";
import { useRoomStore } from "@/stores/roomStore";
import { toastError, toastSuccess, useUiStore } from "@/stores/uiStore";
import type {
  MatchCancelledPayload,
  MatchFinishedPayload,
  MatchStartedPayload,
  PlayerLeftPayload,
  PlayerPresencePayload,
  PlayerReadyPayload,
  QuestionReceivedPayload,
  ServerEnvelope,
  WsProtocolError,
} from "@/types/events";
import type {
  MatchState,
  PublicPlayer,
  Room,
} from "@/types/api";

function playerName(playerId: string | null, fallback = "Someone"): string {
  if (!playerId) {
    return fallback;
  }
  return (
    useRoomStore.getState().players.find((player) => player.id === playerId)?.nickname ??
    fallback
  );
}

function friendlyWsCode(code: string): string {
  switch (code) {
    case "permission_denied":
      return "Not allowed";
    case "conflict":
      return "Action unavailable";
    case "validation_error":
    case "invalid_payload":
      return "Check that action";
    case "duplicate_request":
      return "Already sent";
    case "not_found":
      return "Not found";
    case "message_too_large":
      return "Message too long";
    case "internal_error":
      return "Server error";
    case "invalid_session":
      return "Session expired";
    default:
      return "Action failed";
  }
}

/**
 * Owns the room WebSocket lifecycle and turns each server event into an
 * authoritative state update. No event payload is allowed to create a secret
 * identity, a winner, or a turn owner on the client.
 */
export function useRoomLive(roomCode: string, roomId: string | null, enabled = true): void {
  const wasConnectedRef = useRef(false);
  const authNotifiedRef = useRef(false);

  useEffect(() => {
    if (!enabled || !roomId) {
      return;
    }
    authNotifiedRef.current = false;
    wasConnectedRef.current = false;
    let characterTimer: ReturnType<typeof setTimeout> | null = null;
    let staleMatchCheck = false;

    const scheduleCharacterRefresh = () => {
      if (characterTimer) {
        clearTimeout(characterTimer);
      }
      characterTimer = setTimeout(() => {
        characterTimer = null;
        void useRoomStore.getState().refreshCharacters();
      }, 250);
    };

    const refreshMatchHistory = (matchId?: string) => {
      const id = matchId ?? useMatchStore.getState().state?.match.id;
      if (id) {
        void useMatchStore.getState().syncHistory(id);
      }
    };

    const reconcileEndedOfflineMatch = async (room: Room) => {
      const current = useMatchStore.getState().state;
      if (!current || current.match.phase !== "in_progress") {
        if (room.status === "in_progress") {
          useMatchStore.getState().requestState(0);
        }
        return;
      }
      if (staleMatchCheck) {
        return;
      }
      staleMatchCheck = true;
      try {
        const loaded = await useMatchStore.getState().loadState(current.match.id);
        if (loaded) {
          await useMatchStore.getState().syncHistory(current.match.id);
        }
      } finally {
        staleMatchCheck = false;
      }
    };

    const finishEndedMatch = async (matchId: string | undefined) => {
      if (!matchId) {
        await useRoomStore.getState().refreshRoom();
        return;
      }
      const loaded = await useMatchStore.getState().loadState(matchId);
      if (loaded) {
        await useMatchStore.getState().syncHistory(matchId);
      }
      await useRoomStore.getState().refreshRoom();
    };

    const handleMessage = (message: ServerEnvelope) => {
      useConnectionStore.getState().noteMessage();
      if (message.request_id) {
        usePendingStore.getState().finishByRequestId(message.request_id);
      }
      const payload = message.payload;

      switch (message.event) {
        case "room.state":
        case "room.updated": {
          const room = payload as unknown as Room;
          useRoomStore.getState().applyRoom(room);
          if (message.event === "room.state") {
            void useRoomStore.getState().refreshCollections();
            void reconcileEndedOfflineMatch(room);
          }
          break;
        }

        case "player.joined": {
          useRoomStore.getState().addPlayer(payload as unknown as PublicPlayer);
          break;
        }

        case "player.left": {
          const left = payload as unknown as PlayerLeftPayload;
          const session = useAuthStore.getState().session;
          if (session?.playerId === left.player_id) {
            useAuthStore
              .getState()
              .signOutLocal();
            toastError("You were removed", "You no longer have access to this room.");
            break;
          }
          useRoomStore.getState().removePlayerLocal(left.player_id);
          break;
        }

        case "player.connected":
        case "player.disconnected": {
          const presence = payload as unknown as PlayerPresencePayload;
          useRoomStore
            .getState()
            .setPresence(presence.player_id, message.event === "player.connected");
          break;
        }

        case "player.ready_changed": {
          const ready = payload as unknown as PlayerReadyPayload;
          useRoomStore.getState().applyReady(ready.player_id, ready.ready);
          usePendingStore.getState().finish(`ready:${ready.player_id}`);
          break;
        }

        case "character.added":
        case "character.deleted": {
          if (message.event === "character.deleted") {
            const characterId = payload.character_id;
            if (typeof characterId === "string") {
              useRoomStore.getState().removeCharacterLocal(characterId);
            }
          }
          scheduleCharacterRefresh();
          break;
        }

        case "match.started": {
          const started = payload as unknown as MatchStartedPayload;
          usePendingStore.getState().finish("match_start");
          useRoomStore.getState().setRoomStatus("in_progress");
          const current = useMatchStore.getState().state;
          if (!current || current.match.id !== started.match_id) {
            useMatchStore.getState().requestState(0);
          }
          break;
        }

        case "match.state": {
          const state = payload as unknown as MatchState;
          useMatchStore.getState().setState(state);
          if (state.match.phase === "in_progress") {
            useRoomStore.getState().setRoomStatus("in_progress");
          }
          refreshMatchHistory(state.match.id);
          break;
        }

        case "match.turn_changed": {
          usePendingStore.getState().finish("answer");
          useMatchStore.getState().requestState();
          refreshMatchHistory();
          break;
        }

        case "question.received": {
          const question = payload as unknown as QuestionReceivedPayload;
          useUiStore.getState().pushToast(
            "info",
            `Question from ${playerName(question.author_player_id)}`,
            question.content,
          );
          useMatchStore.getState().requestState();
          break;
        }

        case "answer.received": {
          const answer = payload as unknown as { answer: string; question_id: string };
          useUiStore
            .getState()
            .pushToast("success", "Your question was answered", answer.answer);
          useMatchStore.getState().requestState();
          refreshMatchHistory();
          break;
        }

        case "guess.incorrect": {
          usePendingStore.getState().finish("guess");
          useUiStore
            .getState()
            .pushToast("warning", "Not your character", "Keep asking questions and try again.");
          refreshMatchHistory();
          break;
        }

        case "match.finished": {
          const finished = payload as unknown as MatchFinishedPayload;
          usePendingStore.getState().finish("guess");
          usePendingStore.getState().finish("match_cancel");
          useMatchStore.getState().setEndedReason(finished.reason);
          useRoomStore.getState().setRoomStatus("waiting");
          void finishEndedMatch(useMatchStore.getState().state?.match.id);
          useUiStore
            .getState()
            .pushToast(
              "success",
              "Match finished",
              finished.reason === "correct_guess" ? "A correct guess ended the match." : undefined,
            );
          break;
        }

        case "match.cancelled": {
          const cancelled = payload as unknown as MatchCancelledPayload;
          usePendingStore.getState().finish("match_cancel");
          usePendingStore.getState().finish("guess");
          useMatchStore.getState().setEndedReason(cancelled.reason);
          useRoomStore.getState().setRoomStatus("waiting");
          void finishEndedMatch(useMatchStore.getState().state?.match.id);
          useUiStore
            .getState()
            .pushToast("info", "Match cancelled", cancelled.reason.replaceAll("_", " "));
          break;
        }

        case "error": {
          const error = payload as unknown as WsProtocolError;
          if (error.code === "invalid_session") {
            useAuthStore.getState().markExpired();
          }
          if (error.code === "not_found" && /member/i.test(error.message)) {
            useAuthStore.getState().signOutLocal();
          }
          toastError(
            friendlyWsCode(error.code),
            error.code === "internal_error"
              ? "The server could not complete that action."
              : error.message,
          );
          break;
        }

        case "connection.heartbeat":
        default:
          break;
      }
    };

    realtime.connect({
      roomCode,
      getToken: () => useAuthStore.getState().session?.sessionToken ?? null,
      onMessage: handleMessage,
      onStatus: (status, attempt, detail) => {
        useConnectionStore.getState().setStatus(status, attempt, detail ?? null);
        if (status === "connected") {
          if (wasConnectedRef.current) {
            toastSuccess("Back online", "Your room state has been synchronized.");
          } else {
            wasConnectedRef.current = true;
          }
        }
      },
      onProtocolError: (error: WsProtocolError) => {
        toastError("Connection warning", error.message);
      },
      onAuthRequired: async () => {
        const restored = await useAuthStore.getState().restoreWithReconnect();
        return restored ? (useAuthStore.getState().session?.sessionToken ?? null) : null;
      },
      onAuthFailure: () => {
        if (authNotifiedRef.current) {
          return;
        }
        authNotifiedRef.current = true;
        const auth = useAuthStore.getState();
        if (auth.status === "expired") {
          toastError("Session expired", auth.notice ?? "Join the room again.");
        } else {
          toastError(
            "Could not restore the room connection",
            auth.error ?? "Check your connection, then retry.",
          );
        }
      },
    });

    return () => {
      if (characterTimer) {
        clearTimeout(characterTimer);
      }
      realtime.disconnect();
      wasConnectedRef.current = false;
    };
  }, [enabled, roomCode, roomId]);
}
