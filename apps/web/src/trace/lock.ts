/**
 * Single writer per session (docs/46 §3.5 rule 7) via the Web Locks API.
 * Returns a release function, or null when another tab already holds the lock.
 * Without Web Locks support the lock is granted (best effort).
 */
export async function acquireSessionLock(sessionId: string): Promise<(() => void) | null> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (!locks) return () => {};
  return new Promise((resolve) => {
    void locks.request(`spnc-trace-${sessionId}`, { ifAvailable: true }, (lock) => {
      if (!lock) {
        resolve(null);
        return;
      }
      return new Promise<void>((release) => resolve(() => release()));
    });
  });
}
