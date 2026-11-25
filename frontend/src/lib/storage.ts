interface StoredSessionShape {
  roomId: string;
  roomCode: string;
  playerId: string;
  nickname: string;
  sessionToken: string;
  sessionExpiresAt: string;
  reconnectToken: string;
  reconnectExpiresAt: string;
}

export const SESSION_STORAGE_KEY = "guess-the-character.session.v1";

function storage(): Storage | null {
  try {
    if (typeof window === "undefined" || !window.sessionStorage) {
      return null;
    }
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function readStoredSession(): StoredSessionShape | null {
  const target = storage();
  if (!target) {
    return null;
  }
  try {
    const raw = target.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (!isStoredSession(parsed)) {
      target.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    try {
      target.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // Storage can be unavailable (private mode); nothing to clean up.
    }
    return null;
  }
}

export function writeStoredSession(session: StoredSessionShape): void {
  const target = storage();
  if (!target) {
    return;
  }
  try {
    target.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Storage can be unavailable (private mode, quota). The in-memory session
    // remains usable for this tab; nothing is logged.
  }
}

export function clearStoredSession(): void {
  const target = storage();
  if (!target) {
    return;
  }
  try {
    target.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Ignore inaccessible storage.
  }
}

function isStoredSession(value: unknown): value is StoredSessionShape {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.roomId === "string" &&
    typeof candidate.roomCode === "string" &&
    typeof candidate.playerId === "string" &&
    typeof candidate.nickname === "string" &&
    typeof candidate.sessionToken === "string" &&
    candidate.sessionToken.length > 0 &&
    typeof candidate.sessionExpiresAt === "string" &&
    typeof candidate.reconnectToken === "string" &&
    typeof candidate.reconnectExpiresAt === "string"
  );
}
