import { backoffDelay } from "../trace/backoff";

/**
 * Client of the teacher notification WebSocket (docs/47 §3.4, D4; server: api/endpoints/ws.py).
 * Notifications carry identifiers only; the caller refetches over REST. After every
 * (re)connection `onResync` runs, because messages sent while disconnected are lost
 * (NFR-REALTIME-003).
 */

export interface TeacherNotification {
  type: "signal.created" | "run.completed" | "session.state" | "submission.judged";
  session_id?: string;
  student_id?: string;
  [key: string]: unknown;
}

export type SocketStatus = "connecting" | "live" | "reconnecting" | "auth" | "forbidden" | "closed";

export interface SocketLike {
  readyState: number;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code: number }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  send(data: string): void;
  close(code?: number): void;
}

export interface TeacherSocketOptions {
  url: string;
  getToken(): string | null;
  /** Obtains a new access token after a 4401 close; false ends the socket. */
  refresh(): Promise<boolean>;
  onNotification(n: TeacherNotification): void;
  onResync(): void;
  onStatus?(s: SocketStatus): void;
  createSocket?(url: string): SocketLike;
  random?: () => number;
  baseBackoffMs?: number;
  maxBackoffMs?: number;
}

const OPEN = 1;
const CLOSE_UNAUTHENTICATED = 4401;
const CLOSE_FORBIDDEN = 4403;

export function teacherSocketUrl(loc: Pick<Location, "protocol" | "host"> = window.location): string {
  return `${loc.protocol === "https:" ? "wss" : "ws"}://${loc.host}/api/v1/ws/teacher`;
}

export class TeacherSocket {
  private socket: SocketLike | null = null;
  private classIds = new Set<string>();
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private authenticated = false;

  constructor(private readonly o: TeacherSocketOptions) {
    this.connect();
  }

  /** Subscribes to a class (kept across reconnects). */
  subscribe(classId: string): void {
    if (this.classIds.has(classId)) return;
    this.classIds.add(classId);
    if (this.authenticated) this.send({ type: "subscribe", class_id: classId });
  }

  close(): void {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.socket?.close(1000);
    this.setStatus("closed");
  }

  private setStatus(s: SocketStatus): void {
    this.o.onStatus?.(s);
  }

  private send(msg: object): void {
    if (this.socket?.readyState === OPEN) this.socket.send(JSON.stringify(msg));
  }

  private connect(): void {
    if (this.stopped) return;
    this.authenticated = false;
    this.setStatus(this.attempt ? "reconnecting" : "connecting");
    const s = (this.o.createSocket ?? ((u: string) => new WebSocket(u) as unknown as SocketLike))(this.o.url);
    this.socket = s;
    s.onopen = () => {
      const token = this.o.getToken();
      if (!token) {
        s.close(CLOSE_UNAUTHENTICATED);
        return;
      }
      // The token travels in a message, never in the URL (docs/35 09C)
      s.send(JSON.stringify({ type: "auth", access_token: token }));
    };
    s.onmessage = (ev) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
      } catch {
        return;
      }
      if (msg.type === "authenticated") {
        this.authenticated = true;
        this.attempt = 0;
        this.classIds.forEach((id) => this.send({ type: "subscribe", class_id: id }));
        this.setStatus("live");
        this.o.onResync();
      } else if (typeof msg.type === "string" && msg.type.includes(".")) {
        this.o.onNotification(msg as TeacherNotification);
      }
    };
    s.onerror = () => {};
    s.onclose = (ev) => {
      if (this.stopped || this.socket !== s) return;
      this.authenticated = false;
      if (ev.code === CLOSE_FORBIDDEN) {
        this.setStatus("forbidden");
        return;
      }
      if (ev.code === CLOSE_UNAUTHENTICATED) {
        this.setStatus("reconnecting");
        this.o.refresh().then(
          (ok) => (ok ? this.connect() : this.setStatus("auth")),
          () => this.retryLater(),
        );
        return;
      }
      this.retryLater();
    };
  }

  private retryLater(): void {
    if (this.stopped) return;
    this.setStatus("reconnecting");
    const delay = backoffDelay(this.attempt++, this.o.baseBackoffMs ?? 1000, this.o.maxBackoffMs ?? 30_000, this.o.random);
    this.timer = setTimeout(() => this.connect(), delay);
  }
}
