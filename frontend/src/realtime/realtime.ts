import { RoomSocket, type RoomSocketOptions } from "@/realtime/RoomSocket";

class RealtimeService {
  private active: RoomSocket | null = null;

  connect(options: RoomSocketOptions): RoomSocket {
    this.disconnect();
    const socket = new RoomSocket(options);
    this.active = socket;
    socket.connect();
    return socket;
  }

  disconnect(): void {
    this.active?.close();
    this.active = null;
  }

  get isOpen(): boolean {
    return this.active?.isOpen ?? false;
  }

  send(event: string, payload: Record<string, unknown>, requestId?: string): string | null {
    return this.active?.send(event, payload, requestId) ?? null;
  }

  retryNow(): void {
    this.active?.retryNow();
  }

  // Exposed for focused unit tests without a second live singleton.
  replaceForTests(socket: RoomSocket | null): void {
    this.active = socket;
  }
}

export const realtime = new RealtimeService();
