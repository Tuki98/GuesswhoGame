import { beforeEach, describe, expect, it, vi } from "vitest";

import { withAuth } from "@/api/authorized";
import { ApiError } from "@/api/client";
import { SessionExpiredError } from "@/lib/errors";
import { useAuthStore } from "@/stores/authStore";
import { makeSession, signIn } from "@/test/fixtures";

function apiError(status: number, code: string): ApiError {
  return new ApiError({ status, code, message: "Server refused." });
}

beforeEach(() => {
  signIn();
});

describe("withAuth", () => {
  it("uses the current session token", async () => {
    const request = vi.fn(async (token: string) => token);
    await expect(withAuth(request)).resolves.toBe("session-token-1");
    expect(request).toHaveBeenCalledWith("session-token-1");
  });

  it("fails fast without a session and never calls the request", async () => {
    useAuthStore.setState({ session: null, status: "anonymous" });
    const request = vi.fn(async () => "never");
    await expect(withAuth(request)).rejects.toBeInstanceOf(SessionExpiredError);
    expect(request).not.toHaveBeenCalled();
  });

  it("does not retry permission errors", async () => {
    const request = vi.fn(async () => {
      throw apiError(403, "permission_denied");
    });

    await expect(withAuth(request)).rejects.toMatchObject({ status: 403 });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("rotates credentials once and retries the request", async () => {
    const restore = vi.fn(async () => {
      useAuthStore.setState({
        session: makeSession({ sessionToken: "rotated-token" }),
        status: "authenticated",
      });
      return true;
    });
    useAuthStore.setState({ restoreWithReconnect: restore });

    const request = vi
      .fn<(token: string) => Promise<string>>()
      .mockRejectedValueOnce(apiError(401, "invalid_session"))
      .mockResolvedValueOnce("ok");

    await expect(withAuth(request)).resolves.toBe("ok");
    expect(restore).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenNthCalledWith(1, "session-token-1");
    expect(request).toHaveBeenNthCalledWith(2, "rotated-token");
  });

  it("reports an expired session when recovery is impossible", async () => {
    useAuthStore.setState({
      restoreWithReconnect: vi.fn(async () => {
        useAuthStore.setState({ session: null, status: "expired" });
        return false;
      }),
    });

    const request = vi.fn(async () => {
      throw apiError(401, "invalid_session");
    });

    await expect(withAuth(request)).rejects.toBeInstanceOf(SessionExpiredError);
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("surfaces the storage error instead of a session error when recovery fails online", async () => {
    useAuthStore.setState({
      restoreWithReconnect: vi.fn(async () => {
        useAuthStore.setState({ status: "authenticated", error: "Network unreachable." });
        return false;
      }),
    });

    const request = vi.fn(async () => {
      throw apiError(401, "invalid_session");
    });

    await expect(withAuth(request)).rejects.toThrow("Network unreachable.");
  });

  it("marks the session expired if the retry is also rejected", async () => {
    const markExpired = vi.fn();
    useAuthStore.setState({
      restoreWithReconnect: vi.fn(async () => {
        useAuthStore.setState({
          session: makeSession({ sessionToken: "rotated-token" }),
          status: "authenticated",
        });
        return true;
      }),
      markExpired,
    });

    const request = vi.fn(async () => {
      throw apiError(401, "invalid_session");
    });

    await expect(withAuth(request)).rejects.toBeInstanceOf(SessionExpiredError);
    expect(request).toHaveBeenCalledTimes(2);
    expect(markExpired).toHaveBeenCalledTimes(1);
  });
});
