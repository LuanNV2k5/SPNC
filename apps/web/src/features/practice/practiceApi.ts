import { api, call, type Schemas } from "../../api/client";
import { ApiError } from "../../api/errors";
import { lineCount } from "../../trace";

export type Session = Schemas["SessionResponse"];
export type Run = Schemas["RunResponse"];
export type Submission = Schemas["SubmissionResponse"];
export type Problem = Schemas["ProblemResponse"];

const path = (session_id: string) => ({ params: { path: { session_id } } });

export const getProblem = (problem_id: string) => call(api.GET("/api/v1/problems/{problem_id}", { params: { path: { problem_id } } }));

export const getSamples = (problem_id: string) =>
  call(api.GET("/api/v1/problems/{problem_id}/samples", { params: { path: { problem_id } } }));

export const startSession = (problem_id: string, language: string) =>
  call(api.POST("/api/v1/my/practice/sessions", { body: { problem_id, language } }));

/** Newest ACTIVE practice session of this problem, if any (docs/46 D10). */
export async function findActiveSession(problemId: string): Promise<Session | null> {
  const res = await call(api.GET("/api/v1/my/practice/sessions", { params: { query: { page: 1, size: 100 } } }));
  return res.items.find((s) => s.problem_id === problemId && s.status === "ACTIVE") ?? null;
}

export const endSession = (session_id: string, lastSequence?: number) =>
  call(
    api.POST("/api/v1/my/practice/sessions/{session_id}/end", {
      ...path(session_id),
      body: { termination_source: "STUDENT", last_sequence_number: lastSequence ?? null },
    }),
  );

export const createSnapshot = (session_id: string, reason: "RUN" | "SUBMIT" | "CHECKPOINT", language: string, source_code: string) =>
  call(
    api.POST("/api/v1/my/coding-sessions/{session_id}/snapshots", {
      ...path(session_id),
      body: { reason, language, source_code, line_count: lineCount(source_code) },
    }),
  );

export const createRun = (session_id: string, snapshot_id: string, input: string) =>
  call(api.POST("/api/v1/my/coding-sessions/{session_id}/runs", { ...path(session_id), body: { snapshot_id, input } }));

export const getRun = (session_id: string, run_id: string) =>
  call(api.GET("/api/v1/my/coding-sessions/{session_id}/runs/{run_id}", { params: { path: { session_id, run_id } } }));

export const submit = (session_id: string, snapshot_id: string) =>
  call(api.POST("/api/v1/my/coding-sessions/{session_id}/submissions", { ...path(session_id), body: { snapshot_id } }));

export const getSubmission = (submission_id: string) =>
  call(api.GET("/api/v1/my/submissions/{submission_id}", { params: { path: { submission_id } } }));

export const isFinished = (status: string) => status === "COMPLETED" || status === "FAILED_INTERNAL";

export class PollTimeoutError extends ApiError {
  constructor() {
    super(null, "RESULT_TIMEOUT", "No result yet", "");
  }
}

/** Polls until `done` or the timeout; transient errors are retried until the timeout. */
export async function poll<T>(fetchOnce: () => Promise<T>, done: (v: T) => boolean, intervalMs: number, timeoutMs: number): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    try {
      const v = await fetchOnce();
      if (done(v)) return v;
    } catch (err) {
      if (!(err instanceof ApiError) || (err.status !== null && err.status < 500)) throw err;
    }
    if (Date.now() + intervalMs > deadline) throw new PollTimeoutError();
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
