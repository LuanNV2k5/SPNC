import { api, call, type Schemas } from "../../api/client";
import type { ReplayEvent } from "../../trace";

export type Klass = Schemas["ClassResponse"];
export type Member = Schemas["MemberResponse"];
export type AttentionItem = Schemas["AttentionStudentItem"];
export type ObservedSession = Schemas["ObservedSessionItem"];
export type Signal = Schemas["SignalItem"];
export type Timeline = Schemas["TimelineResponse"];
export type Annotation = Schemas["AnnotationResponse"];
export type SignalStatus = "NEW" | "ACKNOWLEDGED" | "DISMISSED";

/** Every teacher query key starts with "t" so a resync can refetch them all (docs/47 §3.4). */
export const keys = {
  all: ["t"] as const,
  classes: () => ["t", "classes"] as const,
  klass: (c: string) => ["t", "class", c] as const,
  attention: (c: string) => ["t", "attention", c] as const,
  members: (c: string) => ["t", "members", c] as const,
  sessions: (c: string, s: string) => ["t", "sessions", c, s] as const,
  signals: (c: string, s: string) => ["t", "signals", c, s] as const,
  timeline: (sessionId: string) => ["t", "timeline", sessionId] as const,
  annotations: (studentId: string) => ["t", "annotations", studentId] as const,
};

const cs = (class_id: string, student_id: string) => ({ class_id, student_id });

export const listClasses = () => call(api.GET("/api/v1/classes", { params: { query: { page: 1, size: 100 } } }));
export const getClass = (class_id: string) => call(api.GET("/api/v1/classes/{class_id}", { params: { path: { class_id } } }));
export const createClass = (name: string, academic_year: string) => call(api.POST("/api/v1/classes", { body: { name, academic_year } }));
export const rotateInvite = (class_id: string) =>
  call(api.POST("/api/v1/classes/{class_id}/invite-code/rotate", { params: { path: { class_id } } }));
export const listMembers = (class_id: string) =>
  call(api.GET("/api/v1/classes/{class_id}/members", { params: { path: { class_id }, query: { page: 1, size: 100 } } }));
export const listAttention = (class_id: string) =>
  call(api.GET("/api/v1/classes/{class_id}/attention", { params: { path: { class_id }, query: { page: 1, size: 100 } } }));

export const listSessions = (class_id: string, student_id: string) =>
  call(api.GET("/api/v1/classes/{class_id}/students/{student_id}/sessions", { params: { path: cs(class_id, student_id), query: { page: 1, size: 100 } } }));

export const listSignals = (class_id: string, student_id: string, filters: { status?: string; signal_type?: string; session_id?: string }) =>
  call(
    api.GET("/api/v1/classes/{class_id}/students/{student_id}/signals", {
      params: { path: cs(class_id, student_id), query: { page: 1, size: 100, ...filters } },
    }),
  );

export const setSignalStatus = (class_id: string, student_id: string, signal_id: string, status: SignalStatus) =>
  call(api.PATCH("/api/v1/classes/{class_id}/students/{student_id}/signals/{signal_id}", { params: { path: { ...cs(class_id, student_id), signal_id } }, body: { status } }));

const PAGE = 1000;

/** Timeline plus every remaining trace event (docs/47 §3.3 step 1). */
export async function loadTimeline(
  class_id: string,
  student_id: string,
  session_id: string,
  onProgress?: (loaded: number, total: number) => void,
): Promise<{ timeline: Timeline; events: ReplayEvent[] }> {
  const path = { ...cs(class_id, student_id), session_id };
  const timeline = await call(api.GET("/api/v1/classes/{class_id}/students/{student_id}/sessions/{session_id}/timeline", { params: { path, query: { skip: 0, limit: PAGE } } }));
  const events: ReplayEvent[] = [...timeline.events];
  onProgress?.(events.length, timeline.total_events);
  while (events.length < timeline.total_events) {
    const page = await call(
      api.GET("/api/v1/classes/{class_id}/students/{student_id}/sessions/{session_id}/trace-events", { params: { path, query: { skip: events.length, limit: PAGE } } }),
    );
    if (!page.items.length) break;
    events.push(...page.items);
    onProgress?.(events.length, timeline.total_events);
  }
  return { timeline, events };
}

export const getSnapshot = (class_id: string, student_id: string, session_id: string, snapshot_id: string) =>
  call(api.GET("/api/v1/classes/{class_id}/students/{student_id}/sessions/{session_id}/snapshots/{snapshot_id}", { params: { path: { ...cs(class_id, student_id), session_id, snapshot_id } } }));

export const listAnnotations = (student_id: string, session_id?: string) =>
  call(api.GET("/api/v1/annotations", { params: { query: { student_id, session_id, page: 1, size: 100 } } }));
export const createAnnotation = (body: { student_id: string; session_id?: string; signal_id?: string; content: string }) =>
  call(api.POST("/api/v1/annotations", { body }));
export const updateAnnotation = (annotation_id: string, content: string) =>
  call(api.PATCH("/api/v1/annotations/{annotation_id}", { params: { path: { annotation_id } }, body: { content } }));
export const deleteAnnotation = (annotation_id: string) => call(api.DELETE("/api/v1/annotations/{annotation_id}", { params: { path: { annotation_id } } }));
