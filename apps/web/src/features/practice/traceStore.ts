import { openTraceStore, type TraceStore } from "../../trace";

let store: Promise<TraceStore> | null = null;

/** One IndexedDB connection per page. */
export function getTraceStore(): Promise<TraceStore> {
  if (!store) store = openTraceStore();
  return store;
}
