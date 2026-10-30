import { describe, expect, it, vi } from "vitest";
import { TeacherSocket, teacherSocketUrl, type SocketLike, type SocketStatus, type TeacherNotification } from "./teacherSocket";

class FakeSocket implements SocketLike {
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: SocketLike["onopen"] = null;
  onmessage: SocketLike["onmessage"] = null;
  onclose: SocketLike["onclose"] = null;
  onerror: SocketLike["onerror"] = null;
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.readyState = 3;
  }
  open() {
    this.readyState = 1;
    this.onopen?.({});
  }
  receive(msg: object) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  drop(code: number) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

function setup(refresh: () => Promise<boolean> = async () => true) {
  const sockets: FakeSocket[] = [];
  const notes: TeacherNotification[] = [];
  const statuses: SocketStatus[] = [];
  let token = "t1";
  const resync = vi.fn();
  const refreshSpy = vi.fn(async () => {
    token = "t2";
    return refresh();
  });
  const ws = new TeacherSocket({
    url: "ws://x/api/v1/ws/teacher",
    getToken: () => token,
    refresh: refreshSpy,
    onNotification: (n) => notes.push(n),
    onResync: resync,
    onStatus: (s) => statuses.push(s),
    createSocket: () => {
      const s = new FakeSocket();
      sockets.push(s);
      return s;
    },
    baseBackoffMs: 5,
    maxBackoffMs: 20,
    random: () => 1,
  });
  return { ws, sockets, notes, statuses, resync, refreshSpy };
}

const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));

describe("TeacherSocket (docs/47 D4)", () => {
  it("authenticates by message, subscribes, delivers notifications and resyncs", () => {
    const { ws, sockets, notes, statuses, resync } = setup();
    ws.subscribe("c1");
    const s = sockets[0]!;
    s.open();
    expect(s.sent).toEqual([{ type: "auth", access_token: "t1" }]);
    s.receive({ type: "authenticated" });
    expect(s.sent[1]).toEqual({ type: "subscribe", class_id: "c1" });
    expect(resync).toHaveBeenCalledTimes(1);
    expect(statuses.at(-1)).toBe("live");
    s.receive({ type: "subscribed", class_id: "c1" });
    s.receive({ type: "run.completed", run_id: "r", session_id: "s", student_id: "u", verdict: "ACCEPTED", status: "COMPLETED" });
    expect(notes).toHaveLength(1);
    ws.subscribe("c2");
    expect(s.sent[2]).toEqual({ type: "subscribe", class_id: "c2" });
    ws.close();
  });

  it("4401: refreshes the token and reconnects with the new one", async () => {
    const { ws, sockets, refreshSpy, resync } = setup();
    ws.subscribe("c1");
    sockets[0]!.open();
    sockets[0]!.drop(4401);
    await tick();
    expect(refreshSpy).toHaveBeenCalledTimes(1);
    expect(sockets).toHaveLength(2);
    sockets[1]!.open();
    expect(sockets[1]!.sent[0]).toEqual({ type: "auth", access_token: "t2" });
    sockets[1]!.receive({ type: "authenticated" });
    expect(sockets[1]!.sent[1]).toEqual({ type: "subscribe", class_id: "c1" });
    expect(resync).toHaveBeenCalledTimes(1);
    ws.close();
  });

  it("4401 with a failed refresh stops in the auth state; 4403 stops as forbidden", async () => {
    const a = setup(async () => false);
    a.sockets[0]!.open();
    a.sockets[0]!.drop(4401);
    await tick();
    expect(a.statuses.at(-1)).toBe("auth");
    expect(a.sockets).toHaveLength(1);
    const b = setup();
    b.sockets[0]!.drop(4403);
    await tick(30);
    expect(b.statuses.at(-1)).toBe("forbidden");
    expect(b.sockets).toHaveLength(1);
  });

  it("other closes reconnect with backoff and resync after authenticating again", async () => {
    const { ws, sockets, resync, statuses } = setup();
    sockets[0]!.open();
    sockets[0]!.receive({ type: "authenticated" });
    sockets[0]!.drop(1006);
    expect(statuses.at(-1)).toBe("reconnecting");
    await tick(15);
    expect(sockets).toHaveLength(2);
    sockets[1]!.open();
    sockets[1]!.receive({ type: "authenticated" });
    expect(resync).toHaveBeenCalledTimes(2);
    ws.close();
  });

  it("builds a same-origin URL", () => {
    expect(teacherSocketUrl({ protocol: "https:", host: "spnc.example" })).toBe("wss://spnc.example/api/v1/ws/teacher");
    expect(teacherSocketUrl({ protocol: "http:", host: "127.0.0.1:8080" })).toBe("ws://127.0.0.1:8080/api/v1/ws/teacher");
  });
});
