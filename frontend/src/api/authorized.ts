import { ApiError } from "@/api/client";
import { errorMessage, SessionExpiredError } from "@/lib/errors";
import { useAuthStore } from "@/stores/authStore";

/**
 * Run an authenticated request, rotating credentials through the backend's
 * reconnect endpoint if the session expired. Every caller gets at most one
 * automatic retry; permission and domain errors are never retried.
 */
export async function withAuth<T>(request: (token: string) => Promise<T>): Promise<T> {
  const session = useAuthStore.getState().session;
  if (!session) {
    throw new SessionExpiredError();
  }

  try {
    return await request(session.sessionToken);
  } catch (error) {
    if (!(error instanceof ApiError) || !error.isInvalidSession) {
      throw error;
    }

    const restored = await useAuthStore.getState().restoreWithReconnect();
    if (!restored) {
      const current = useAuthStore.getState();
      if (current.status === "expired") {
        throw new SessionExpiredError();
      }
      throw new Error(current.error ?? errorMessage(error));
    }

    const next = useAuthStore.getState().session;
    if (!next) {
      throw new SessionExpiredError();
    }
    try {
      return await request(next.sessionToken);
    } catch (retryError) {
      if (retryError instanceof ApiError && retryError.isInvalidSession) {
        useAuthStore.getState().markExpired();
        throw new SessionExpiredError();
      }
      throw retryError;
    }
  }
}
