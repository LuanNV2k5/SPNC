import type { Schemas } from "../../api/client";

export function participantDeadline(
  exam: Pick<Schemas["ExamResponse"], "end_time" | "duration_minutes">,
  participation: Pick<Schemas["ParticipationResponse"], "started_at">,
): number | null {
  if (!participation.started_at) return null;
  const durationEnd = exam.duration_minutes == null
    ? Number.POSITIVE_INFINITY
    : Date.parse(participation.started_at) + exam.duration_minutes * 60_000;
  return Math.min(durationEnd, Date.parse(exam.end_time));
}
