import { openDB, type DBSchema, type IDBPDatabase } from "idb";
import type { StoredEvent } from "./types";

/** Per-session bookkeeping kept next to the events (docs/46 §3.5 rules 1, 6). */
export interface SessionMeta {
  session_id: string;
  user_id: string;
  problem_id: string;
  language: string;
  /** Highest sequence the server acknowledged; keeps numbering monotonic after the queue empties. */
  acked_through: number;
}

export interface Draft {
  session_id: string;
  user_id: string;
  content: string;
  updated_at: string;
}

interface TraceDB extends DBSchema {
  events: { key: [string, number]; value: StoredEvent };
  sessions: { key: string; value: SessionMeta; indexes: { by_user: string } };
  drafts: { key: string; value: Draft; indexes: { by_user: string } };
}

export interface TraceStore {
  putEvent(e: StoredEvent): Promise<void>;
  pending(sessionId: string): Promise<StoredEvent[]>;
  /** Deletes events with sequence ≤ `through` and records `through` as acknowledged. */
  ack(sessionId: string, through: number): Promise<void>;
  maxEventSequence(sessionId: string): Promise<number>;
  getMeta(sessionId: string): Promise<SessionMeta | undefined>;
  putMeta(meta: SessionMeta): Promise<void>;
  sessionsOf(userId: string): Promise<SessionMeta[]>;
  getDraft(sessionId: string): Promise<Draft | undefined>;
  putDraft(d: Draft): Promise<void>;
  deleteSession(sessionId: string): Promise<void>;
  /** Number of unacknowledged events across all sessions of a user. */
  pendingCountOf(userId: string): Promise<number>;
  clearUser(userId: string): Promise<void>;
}

const range = (sessionId: string, from: number, to: number) =>
  IDBKeyRange.bound([sessionId, from], [sessionId, to]);

export async function openTraceStore(name = "spnc-trace"): Promise<TraceStore> {
  const db: IDBPDatabase<TraceDB> = await openDB<TraceDB>(name, 1, {
    upgrade(d) {
      d.createObjectStore("events", { keyPath: ["session_id", "sequence_number"] });
      d.createObjectStore("sessions", { keyPath: "session_id" }).createIndex("by_user", "user_id");
      d.createObjectStore("drafts", { keyPath: "session_id" }).createIndex("by_user", "user_id");
    },
  });

  const store: TraceStore = {
    async putEvent(e) {
      await db.put("events", e);
    },
    async pending(sessionId) {
      return db.getAll("events", range(sessionId, 0, Number.MAX_SAFE_INTEGER));
    },
    async ack(sessionId, through) {
      const tx = db.transaction(["events", "sessions"], "readwrite");
      await tx.objectStore("events").delete(range(sessionId, 0, through));
      const meta = await tx.objectStore("sessions").get(sessionId);
      if (meta && meta.acked_through < through) await tx.objectStore("sessions").put({ ...meta, acked_through: through });
      await tx.done;
    },
    async maxEventSequence(sessionId) {
      const cursor = await db.transaction("events").store.openCursor(range(sessionId, 0, Number.MAX_SAFE_INTEGER), "prev");
      return cursor ? cursor.value.sequence_number : 0;
    },
    getMeta: (sessionId) => db.get("sessions", sessionId),
    async putMeta(meta) {
      await db.put("sessions", meta);
    },
    sessionsOf: (userId) => db.getAllFromIndex("sessions", "by_user", userId),
    getDraft: (sessionId) => db.get("drafts", sessionId),
    async putDraft(d) {
      await db.put("drafts", d);
    },
    async deleteSession(sessionId) {
      const tx = db.transaction(["events", "sessions", "drafts"], "readwrite");
      await tx.objectStore("events").delete(range(sessionId, 0, Number.MAX_SAFE_INTEGER));
      await tx.objectStore("sessions").delete(sessionId);
      await tx.objectStore("drafts").delete(sessionId);
      await tx.done;
    },
    async pendingCountOf(userId) {
      let n = 0;
      for (const m of await store.sessionsOf(userId)) {
        n += await db.count("events", range(m.session_id, 0, Number.MAX_SAFE_INTEGER));
      }
      return n;
    },
    async clearUser(userId) {
      const ids = new Set([
        ...(await store.sessionsOf(userId)).map((m) => m.session_id),
        ...(await db.getAllKeysFromIndex("drafts", "by_user", userId)),
      ]);
      for (const id of ids) await store.deleteSession(id);
    },
  };
  return store;
}
