import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest, mediaUrl } from "@/api/client";
import { API_TIMEOUT_MS } from "@/config";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("apiRequest", () => {
  it("sends the bearer token and parses JSON without exposing it in the URL", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ rooms: [] }));

    await expect(apiRequest("/api/rooms/abc", { token: "secret-token" })).resolves.toEqual({
      rooms: [],
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/rooms/abc");
    expect(url).not.toContain("secret-token");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer secret-token");
    expect(init.credentials).toBe("omit");
    expect(init.method).toBe("GET");
  });

  it("serializes JSON bodies and sets the content type", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await apiRequest("/api/rooms", { method: "POST", body: { nickname: "Maya" } });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ nickname: "Maya" }));
    expect(init.method).toBe("POST");
  });

  it("sends multipart form data without a JSON content type", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "character-1" }));
    const form = new FormData();
    form.append("name", "Pikachu");

    await apiRequest("/api/rooms/abc/characters", {
      method: "POST",
      formData: form,
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBe(form);
    expect(new Headers(init.headers).get("Content-Type")).toBeNull();
  });

  it("returns undefined for 204 and empty responses", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(apiRequest("/api/rooms/abc/leave", { method: "POST" })).resolves.toBeUndefined();

    fetchMock.mockResolvedValueOnce(new Response("", { status: 200 }));
    await expect(apiRequest("/api/rooms/abc")).resolves.toBeUndefined();
  });

  it("parses a structured error envelope and flags invalid sessions", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "invalid_session", message: "Your session expired." } },
        401,
      ),
    );

    const error = await apiRequest("/api/rooms/abc").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(401);
    expect(apiError.code).toBe("invalid_session");
    expect(apiError.isInvalidSession).toBe(true);
    expect(apiError.userMessage).toBe("Your session expired.");
  });

  it("falls back to invalid_session for a 401 without a body", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 401 }));

    const error = (await apiRequest("/api/rooms/abc").catch(
      (caught: unknown) => caught,
    )) as ApiError;

    expect(error.code).toBe("invalid_session");
    expect(error.message).toBe("Your session is invalid or has expired.");
  });

  it("hides internal server details from the user", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "internal_error", message: "Traceback: secret sql" } },
        500,
      ),
    );

    const error = (await apiRequest("/api/rooms/abc").catch(
      (caught: unknown) => caught,
    )) as ApiError;

    expect(error.code).toBe("internal_error");
    expect(error.userMessage).toBe("The game server hit a problem. Please try again.");
  });

  it("summarizes the first validation detail with its location", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "validation_error",
            message: "Request validation failed.",
            details: [
              { location: ["body", "nickname"], message: "Too short." },
              { location: ["body", "code"], message: "Invalid." },
            ],
          },
        },
        422,
      ),
    );

    const error = (await apiRequest("/api/rooms").catch((caught: unknown) => caught)) as ApiError;

    expect(error.userMessage).toBe("nickname: Too short.");
  });

  it("maps aborts to a timeout error", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );

    const pending = apiRequest("/api/rooms/abc");
    const assertion = expect(pending).rejects.toMatchObject({
      status: 0,
      code: "timeout",
    });
    await vi.advanceTimersByTimeAsync(API_TIMEOUT_MS + 1);
    await assertion;
  });

  it("maps transport failures to a network error", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(apiRequest("/api/rooms/abc")).rejects.toMatchObject({
      status: 0,
      code: "network_error",
    });
  });
});

describe("mediaUrl", () => {
  it("returns null for empty values", () => {
    expect(mediaUrl(null)).toBeNull();
    expect(mediaUrl(undefined)).toBeNull();
    expect(mediaUrl("")).toBeNull();
  });

  it("leaves absolute URLs untouched and prefixes relative ones", () => {
    expect(mediaUrl("https://cdn.example.com/a.webp")).toBe("https://cdn.example.com/a.webp");
    expect(mediaUrl("/media/a.webp")).toBe("http://localhost:8000/media/a.webp");
    expect(mediaUrl("media/a.webp")).toBe("http://localhost:8000/media/a.webp");
  });
});
