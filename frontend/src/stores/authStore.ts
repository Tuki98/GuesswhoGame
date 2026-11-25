import { create } from "zustand";

import { ApiError } from "@/api/client";
import { api } from "@/api/endpoints";
import { errorMessage } from "@/lib/errors";
import {
  clearStoredSession,
  readStoredSession,
  writeStoredSession,
} from "@/lib/storage";
import type { PublicPlayer, Room, RoomSessionResponse } from "@/types/api";

export interface AppSession {
  roomId: string;
  roomCode: string;
  playerId: string;
  nickname: string;
  sessionToken: string;
  sessionExpiresAt: string;
  reconnectToken: string;
  reconnectExpiresAt: string;
}

export type AuthStatus = "loading" | "anonymous" | "authenticated" | "expired";

interface AuthState {
  session: AppSession | null;
  status: AuthStatus;
  notice: string | null;
  error: string | null;
  bootstrap: () => Promise<void>;
  establish: (response: RoomSessionResponse) => void;
  createRoom: (input: {
    nickname: string;
    settings: { max_players: number; game_mode: "individual" | "team" };
  }) => Promise<RoomSessionResponse>;
  joinRoom: (input: { code: string; nickname: string }) => Promise<RoomSessionResponse>;
  restoreWithReconnect: () => Promise<boolean>;
  updateRoom: (room: Room) => void;
  updatePlayer: (player: Pick<PublicPlayer, "id" | "nickname">) => void;
  signOutLocal: () => void;
  markExpired: (message?: string) => void;
  setNotice: (notice: string | null) => void;
}

function fromResponse(response: RoomSessionResponse): AppSession {
  return {
    roomId: response.room.id,
    roomCode: response.room.code,
    playerId: response.player.id,
    nickname: response.player.nickname,
    sessionToken: response.credentials.session_token,
    sessionExpiresAt: response.credentials.session_expires_at,
    reconnectToken: response.credentials.reconnect_token,
    reconnectExpiresAt: response.credentials.reconnect_expires_at,
  };
}

function persist(session: AppSession | null): void {
  if (!session) {
    clearStoredSession();
    return;
  }
  writeStoredSession({
    roomId: session.roomId,
    roomCode: session.roomCode,
    playerId: session.playerId,
    nickname: session.nickname,
    sessionToken: session.sessionToken,
    sessionExpiresAt: session.sessionExpiresAt,
    reconnectToken: session.reconnectToken,
    reconnectExpiresAt: session.reconnectExpiresAt,
  });
}

function isExpired(value: string): boolean {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) || parsed <= Date.now() + 2_000;
}

let bootstrapPromise: Promise<void> | null = null;
let reconnectPromise: Promise<boolean> | null = null;

export const useAuthStore = create<AuthState>()((set, get) => ({
  session: null,
  status: "loading",
  notice: null,
  error: null,

  bootstrap: async () => {
    if (bootstrapPromise) {
      return bootstrapPromise;
    }
    bootstrapPromise = (async () => {
      const stored = readStoredSession();
      if (!stored) {
        set({ session: null, status: "anonymous", error: null });
        return;
      }
      const session: AppSession = stored;
      set({ session, status: "loading", error: null });

      if (isExpired(session.sessionExpiresAt)) {
        const restored = await get().restoreWithReconnect();
        if (!restored) {
          set({ status: "expired" });
        }
        return;
      }

      try {
        await api.getRoom(session.roomId, session.sessionToken);
        set({ status: "authenticated", error: null });
      } catch (error) {
        if (error instanceof ApiError && error.isInvalidSession) {
          const restored = await get().restoreWithReconnect();
          if (!restored) {
            set({ status: "expired" });
          }
          return;
        }
        // A network outage must not destroy a still-valid credential. The room
        // screen will show its own offline state and can retry.
        set({
          status: "authenticated",
          error: errorMessage(error),
        });
      }
    })().finally(() => {
      bootstrapPromise = null;
    });
    return bootstrapPromise;
  },

  establish: (response) => {
    const session = fromResponse(response);
    persist(session);
    set({
      session,
      status: "authenticated",
      notice: null,
      error: null,
    });
  },

  createRoom: async (input) => {
    const response = await api.createRoom(input);
    get().establish(response);
    return response;
  },

  joinRoom: async (input) => {
    const response = await api.joinRoom(input);
    get().establish(response);
    return response;
  },

  restoreWithReconnect: async () => {
    if (reconnectPromise) {
      return reconnectPromise;
    }
    const session = get().session ?? readStoredSession();
    if (!session) {
      set({ session: null, status: "expired", error: "No session is available." });
      return false;
    }
    if (isExpired(session.reconnectExpiresAt)) {
      persist(null);
      set({
        session: null,
        status: "expired",
        notice: "Your session and recovery window have expired. Join the room again.",
        error: null,
      });
      return false;
    }

    set({ status: "loading", error: null });
    reconnectPromise = (async () => {
      try {
        const response = await api.reconnect(session.reconnectToken);
        get().establish(response);
        return true;
      } catch (error) {
        if (error instanceof ApiError && (error.isInvalidSession || error.status === 422)) {
          persist(null);
          set({
            session: null,
            status: "expired",
            notice: "Your session could not be restored. Join the room again.",
            error: null,
          });
          return false;
        }
        set({
          status: "authenticated",
          error: errorMessage(error),
          notice: "Could not restore the session. Check your connection and retry.",
        });
        return false;
      }
    })().finally(() => {
      reconnectPromise = null;
    });
    return reconnectPromise;
  },

  updateRoom: (room) => {
    const current = get().session;
    if (!current || current.roomId !== room.id) {
      return;
    }
    const next: AppSession = {
      ...current,
      roomCode: room.code,
    };
    persist(next);
    set({ session: next });
  },

  updatePlayer: (player) => {
    const current = get().session;
    if (!current || current.playerId !== player.id) {
      return;
    }
    const next: AppSession = { ...current, nickname: player.nickname };
    persist(next);
    set({ session: next });
  },

  signOutLocal: () => {
    persist(null);
    set({ session: null, status: "anonymous", notice: null, error: null });
  },

  markExpired: (message = "Your session expired. Join the room again.") => {
    persist(null);
    set({
      session: null,
      status: "expired",
      notice: message,
      error: null,
    });
  },

  setNotice: (notice) => set({ notice }),
}));
