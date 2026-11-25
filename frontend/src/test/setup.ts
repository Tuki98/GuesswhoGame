import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { realtime } from "@/realtime/realtime";

/**
 * Stores are imported lazily so that setup never loads application modules
 * before a test file's `vi.mock()` factories are registered. Loading them
 * statically here would evaluate the real API modules early and bypass mocks.
 */
afterEach(async () => {
  cleanup();
  window.sessionStorage.clear();
  window.localStorage.clear();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  realtime.replaceForTests(null);

  const [
    { useAuthStore },
    { useConnectionStore },
    { useMatchStore },
    { usePendingStore },
    { useRoomStore },
    { useUiStore },
  ] = await Promise.all([
    import("@/stores/authStore"),
    import("@/stores/connectionStore"),
    import("@/stores/matchStore"),
    import("@/stores/pendingStore"),
    import("@/stores/roomStore"),
    import("@/stores/uiStore"),
  ]);

  usePendingStore.getState().clear();
  useUiStore.getState().clearToasts();
  useMatchStore.getState().reset();
  useRoomStore.getState().reset();
  useConnectionStore.getState().reset();
  useAuthStore.setState({
    session: null,
    status: "anonymous",
    notice: null,
    error: null,
  });
});

if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

if (!window.scrollTo) {
  Object.defineProperty(window, "scrollTo", { writable: true, value: vi.fn() });
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
