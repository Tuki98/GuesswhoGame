import { create } from "zustand";

import { api } from "@/api/endpoints";
import { withAuth } from "@/api/authorized";
import { errorMessage } from "@/lib/errors";
import { dispatchSocketAction } from "@/realtime/actions";
import { useAuthStore } from "@/stores/authStore";
import { usePendingStore } from "@/stores/pendingStore";
import { toastError, toastSuccess } from "@/stores/uiStore";
import type {
  Character,
  CreateCharacterPayload,
  GameMode,
  PublicPlayer,
  Room,
  Team,
} from "@/types/api";

interface RoomState {
  room: Room | null;
  players: PublicPlayer[];
  teams: Team[];
  characters: Character[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  load: (roomId: string) => Promise<void>;
  refreshRoom: () => Promise<void>;
  refreshPlayers: () => Promise<void>;
  refreshTeams: () => Promise<void>;
  refreshCharacters: () => Promise<void>;
  refreshCollections: () => Promise<void>;
  applyRoom: (room: Room) => void;
  setRoomStatus: (status: Room["status"]) => void;
  addPlayer: (player: PublicPlayer) => void;
  removePlayerLocal: (playerId: string) => void;
  setPresence: (playerId: string, connected: boolean) => void;
  applyReady: (playerId: string, ready: boolean) => void;
  setReady: (ready: boolean, targetPlayerId?: string) => string | null;

  upsertCharacter: (character: Character) => void;
  removeCharacterLocal: (characterId: string) => void;
  updateSettings: (settings: {
    max_players?: number;
    game_mode?: GameMode;
  }) => Promise<boolean>;
  removePlayer: (playerId: string) => Promise<boolean>;
  leaveRoom: () => Promise<boolean>;
  closeRoom: () => Promise<boolean>;
  createTeam: (name: string) => Promise<boolean>;
  assignTeam: (playerId: string, teamId: string | null) => Promise<boolean>;
  addCharacter: (
    payload: CreateCharacterPayload & { image_url?: string },
    image?: File,
  ) => Promise<boolean>;
  deleteCharacter: (characterId: string) => Promise<boolean>;
  setError: (error: string | null) => void;
  reset: () => void;
}

let loadVersion = 0;
let playersVersion = 0;
let charactersVersion = 0;
let teamsVersion = 0;

const initialState = {
  room: null as Room | null,
  players: [] as PublicPlayer[],
  teams: [] as Team[],
  characters: [] as Character[],
  loading: false,
  refreshing: false,
  error: null as string | null,
};

function sortPlayers(players: PublicPlayer[]): PublicPlayer[] {
  return [...players].sort((left, right) => {
    if (left.is_host !== right.is_host) {
      return left.is_host ? -1 : 1;
    }
    return new Date(left.joined_at).getTime() - new Date(right.joined_at).getTime();
  });
}

export const useRoomStore = create<RoomState>()((set, get) => ({
  ...initialState,

  load: async (roomId) => {
    const version = ++loadVersion;
    const current = get().room;
    set({
      loading: current?.id !== roomId,
      refreshing: current?.id === roomId,
      error: null,
      ...(current?.id !== roomId
        ? { room: null, players: [], teams: [], characters: [] }
        : {}),
    });
    try {
      const [room, players, characters, teams] = await Promise.all([
        withAuth((token) => api.getRoom(roomId, token)),
        withAuth((token) => api.listPlayers(roomId, token)),
        withAuth((token) => api.listCharacters(roomId, token)),
        withAuth((token) => api.listTeams(roomId, token)),
      ]);
      if (version !== loadVersion) {
        return;
      }
      set({
        room,
        players: sortPlayers(players.players),
        characters: characters.characters,
        teams: teams.teams,
        loading: false,
        refreshing: false,
        error: null,
      });
      useAuthStore.getState().updateRoom(room);
    } catch (error) {
      if (version !== loadVersion) {
        return;
      }
      set({
        loading: false,
        refreshing: false,
        error: errorMessage(error),
      });
    }
  },

  refreshRoom: async () => {
    const roomId = get().room?.id;
    if (!roomId) {
      return;
    }
    try {
      const room = await withAuth((token) => api.getRoom(roomId, token));
      get().applyRoom(room);
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },

  refreshPlayers: async () => {
    const roomId = get().room?.id;
    if (!roomId) {
      return;
    }
    const version = ++playersVersion;
    try {
      const response = await withAuth((token) => api.listPlayers(roomId, token));
      if (version !== playersVersion) {
        return;
      }
      set({
        players: sortPlayers(response.players),
        room: get().room
          ? { ...get().room!, player_count: response.players.length }
          : null,
      });
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },

  refreshTeams: async () => {
    const roomId = get().room?.id;
    if (!roomId) {
      return;
    }
    const version = ++teamsVersion;
    try {
      const response = await withAuth((token) => api.listTeams(roomId, token));
      if (version !== teamsVersion) {
        return;
      }
      set({ teams: response.teams });
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },

  refreshCharacters: async () => {
    const roomId = get().room?.id;
    if (!roomId) {
      return;
    }
    const version = ++charactersVersion;
    try {
      const response = await withAuth((token) => api.listCharacters(roomId, token));
      if (version !== charactersVersion) {
        return;
      }
      set({ characters: response.characters });
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },

  refreshCollections: async () => {
    await Promise.all([get().refreshPlayers(), get().refreshTeams(), get().refreshCharacters()]);
  },

  applyRoom: (room) => {
    const current = get().room;
    if (current && current.id !== room.id) {
      return;
    }
    set({ room });
    useAuthStore.getState().updateRoom(room);
  },

  setRoomStatus: (status) => {
    const room = get().room;
    if (!room) {
      return;
    }
    const next = { ...room, status };
    set({ room: next });
    useAuthStore.getState().updateRoom(next);
  },

  addPlayer: (player) => {
    const existing = get().players;
    const nextPlayers = existing.some((row) => row.id === player.id)
      ? existing.map((row) => (row.id === player.id ? player : row))
      : [...existing, player];
    const room = get().room;
    set({
      players: sortPlayers(nextPlayers),
      room: room ? { ...room, player_count: nextPlayers.length } : null,
    });
  },

  removePlayerLocal: (playerId) => {
    const previous = get().players;
    const players = previous.filter((player) => player.id !== playerId);
    if (players.length === previous.length) {
      return;
    }
    const room = get().room;
    set({
      players,
      teams: get().teams.map((team) => ({
        ...team,
        members: team.members.filter((member) => member.id !== playerId),
      })),
      room: room ? { ...room, player_count: players.length } : null,
    });
  },

  setPresence: (playerId, connected) => {
    set((state) => ({
      players: state.players.map((player) =>
        player.id === playerId ? { ...player, is_connected: connected } : player,
      ),
    }));
  },

  applyReady: (playerId, ready) => {
    set((state) => ({
      players: state.players.map((player) =>
        player.id === playerId ? { ...player, is_ready: ready } : player,
      ),
      teams: state.teams.map((team) => ({
        ...team,
        members: team.members.map((member) =>
          member.id === playerId ? { ...member, is_ready: ready } : member,
        ),
      })),
    }));
  },

  setReady: (ready, targetPlayerId) => {
    const session = useAuthStore.getState().session;
    const target = targetPlayerId ?? session?.playerId;
    if (!session || !target) {
      toastError("Could not update readiness", "Your session is not available.");
      return null;
    }
    const payload: Record<string, unknown> = { ready };
    if (target !== session.playerId) {
      payload.target_player_id = target;
    }
    const key = `ready:${target}`;
    const requestId = dispatchSocketAction("player.set_ready", payload, {
      key,
      label: "Updating readiness",
    });
    if (!requestId) {
      usePendingStore.getState().finish(key);
      return null;
    }
    // Readiness has no direct ack; the room broadcast is authoritative.
    window.setTimeout(() => usePendingStore.getState().finish(key), 1_500);
    return requestId;
  },
  upsertCharacter: (character) => {
    set((state) => {
      const exists = state.characters.some((row) => row.id === character.id);
      return {
        characters: exists
          ? state.characters.map((row) => (row.id === character.id ? character : row))
          : [...state.characters, character],
      };
    });
  },

  removeCharacterLocal: (characterId) => {
    set((state) => ({
      characters: state.characters.filter((character) => character.id !== characterId),
    }));
  },

  updateSettings: async (settings) => {
    const room = get().room;
    if (!room) {
      return false;
    }
    try {
      const updated = await withAuth((token) =>
        api.updateSettings(room.id, token, settings),
      );
      get().applyRoom(updated);
      toastSuccess("Room settings saved");
      return true;
    } catch (error) {
      toastError("Could not update settings", errorMessage(error));
      return false;
    }
  },

  removePlayer: async (playerId) => {
    const room = get().room;
    if (!room) {
      return false;
    }
    try {
      await withAuth((token) => api.removePlayer(room.id, playerId, token));
      get().removePlayerLocal(playerId);
      toastSuccess("Player removed");
      return true;
    } catch (error) {
      toastError("Could not remove player", errorMessage(error));
      return false;
    }
  },

  leaveRoom: async () => {
    const room = get().room;
    if (!room) {
      return false;
    }
    try {
      await withAuth((token) => api.leaveRoom(room.id, token));
      useAuthStore.getState().signOutLocal();
      get().reset();
      toastSuccess("You left the room");
      return true;
    } catch (error) {
      toastError("Could not leave the room", errorMessage(error));
      return false;
    }
  },

  closeRoom: async () => {
    const room = get().room;
    if (!room) {
      return false;
    }
    try {
      const updated = await withAuth((token) => api.closeRoom(room.id, token));
      get().applyRoom(updated);
      toastSuccess("Room closed");
      return true;
    } catch (error) {
      toastError("Could not close the room", errorMessage(error));
      return false;
    }
  },

  createTeam: async (name) => {
    const room = get().room;
    if (!room) {
      return false;
    }
    try {
      const team = await withAuth((token) => api.createTeam(room.id, token, name));
      set((state) => ({ teams: [...state.teams, team] }));
      toastSuccess(`Team ${team.name} created`);
      return true;
    } catch (error) {
      toastError("Could not create team", errorMessage(error));
      return false;
    }
  },

  assignTeam: async (playerId, teamId) => {
    const room = get().room;
    if (!room) {
      return false;
    }
    try {
      await withAuth((token) => api.assignTeam(room.id, playerId, token, teamId));
      await Promise.all([get().refreshTeams(), get().refreshPlayers()]);
      toastSuccess(teamId ? "Player assigned to team" : "Player removed from team");
      return true;
    } catch (error) {
      toastError("Could not assign team", errorMessage(error));
      return false;
    }
  },

  addCharacter: async (payload, image) => {
    const room = get().room;
    if (!room) {
      return false;
    }
    try {
      let created: Character;
      if (image) {
        created = await withAuth((token) =>
          api.createCharacter(room.id, token, payload, image),
        );
      } else if (payload.image_url) {
        created = await withAuth((token) =>
          api.createCharacter(room.id, token, {
            name: payload.name,
            franchise: payload.franchise,
            category: payload.category,
            attributes: payload.attributes,
            image_url: payload.image_url!,
          }),
        );
      } else {
        toastError("Could not add character", "Choose an image file or provide an image URL.");
        return false;
      }
      get().upsertCharacter(created);
      toastSuccess("Character added", created.name);
      return true;
    } catch (error) {
      toastError("Could not add character", errorMessage(error));
      return false;
    }
  },

  deleteCharacter: async (characterId) => {
    const room = get().room;
    if (!room) {
      return false;
    }
    try {
      await withAuth((token) => api.deleteCharacter(room.id, characterId, token));
      get().removeCharacterLocal(characterId);
      toastSuccess("Character removed");
      return true;
    } catch (error) {
      toastError("Could not remove character", errorMessage(error));
      return false;
    }
  },

  setError: (error) => set({ error }),

  reset: () => {
    loadVersion += 1;
    playersVersion += 1;
    charactersVersion += 1;
    teamsVersion += 1;
    set({ ...initialState });
  },
}));
