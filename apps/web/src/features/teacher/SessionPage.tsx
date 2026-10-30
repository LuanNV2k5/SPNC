import { Alert, Badge, Box, Button, Grid, Group, Loader, Paper, ScrollArea, Slider, Stack, Switch, Table, Text, Title } from "@mantine/core";
import { DiffEditor, Editor } from "@monaco-editor/react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { t, tt } from "../../i18n/vi";
import { Replay, type ReplayEvent, type SnapshotPoint, type Verification } from "../../trace";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { Annotations } from "./Annotations";
import { LiveBadge } from "./LiveBadge";
import { useLive } from "./LiveProvider";
import { SignalCard } from "./SignalCard";
import { getSnapshot, keys, loadTimeline, type Signal } from "./teacherApi";

const MONACO_LANGUAGE: Record<string, string> = { CPP17: "cpp", PYTHON3: "python" };
const ACTIVE_REFRESH_MS = 15_000; // keystrokes never travel over the socket (docs/47 F5)
const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("vi-VN") : "—");
const fmtTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleTimeString("vi-VN") : "");

// Snapshots are immutable (REQ-TRACE-014): fetch each one once per page load
const snapshotCache = new Map<string, Promise<{ source_code?: string | null; content_available: boolean }>>();
const cachedSnapshot = (c: string, st: string, se: string, id: string) => {
  if (!snapshotCache.has(id)) snapshotCache.set(id, getSnapshot(c, st, se, id).catch((e) => (snapshotCache.delete(id), Promise.reject(e))));
  return snapshotCache.get(id)!;
};

type StoredEvent = ReplayEvent & { id: string; server_timestamp: string };

function describe(e: ReplayEvent): string {
  const p = e.payload;
  const label = tt.eventType[e.event_type] ?? e.event_type;
  switch (e.event_type) {
    case "EDITOR_CHANGED": {
      const text = typeof p.text === "string" ? p.text : "";
      const shown = text.length > 24 ? `${text.slice(0, 24)}…` : text;
      return `${label} · ${String(p.operation_type)} ${JSON.stringify(shown)}${p.input_source === "paste" ? " · dán" : ""}`;
    }
    case "RUN_REQUESTED":
      return `${label}${p.input_used ? ` · input ${JSON.stringify(String(p.input_used).slice(0, 16))}` : ""}`;
    case "RUN_COMPLETED":
      return `${label} · ${p.verdict ? (t.verdicts[String(p.verdict)] ?? String(p.verdict)) : String(p.status)}`;
    default:
      return label;
  }
}

/** Sequence closest to an instant (signal evidence → timeline point). */
function sequenceAt(events: StoredEvent[], iso: unknown): number | null {
  if (typeof iso !== "string") return null;
  const at = new Date(iso).getTime();
  let best: number | null = null;
  for (const e of events) {
    if (new Date(e.server_timestamp).getTime() <= at) best = e.sequence_number;
    else break;
  }
  return best ?? events[0]?.sequence_number ?? null;
}

function signalSequence(events: StoredEvent[], s: Signal): number | null {
  const ev = s.evidence as Record<string, unknown>;
  for (const idKey of ["first_code_event_id", "meaningful_event_before_id"]) {
    const hit = events.find((e) => e.id === ev[idKey]);
    if (hit) return hit.sequence_number;
  }
  const runId = Array.isArray(ev.run_ids) ? ev.run_ids[ev.run_ids.length - 1] : undefined;
  const run = events.find((e) => e.event_type === "RUN_REQUESTED" && e.payload.run_id === runId);
  if (run) return run.sequence_number;
  return sequenceAt(events, ev.first_code_event_time ?? ev.start_time ?? ev.time_range_end ?? s.detected_at);
}

export function SessionPage() {
  const { classId = "", studentId = "", sessionId = "" } = useParams();
  const live = useLive();
  useEffect(() => live.watch(classId), [live, classId]);
  const [progress, setProgress] = useState<[number, number] | null>(null);

  const q = useQuery({
    queryKey: keys.timeline(sessionId),
    queryFn: () => loadTimeline(classId, studentId, sessionId, (a, b) => setProgress([a, b])),
    refetchInterval: (query) => (query.state.data?.timeline.session.status === "ACTIVE" ? ACTIVE_REFRESH_MS : false),
  });
  const timeline = q.data?.timeline;
  const events = (q.data?.events ?? []) as StoredEvent[];
  const replay = useMemo(
    () => (q.data ? new Replay(q.data.events, { highestContiguous: q.data.timeline.state.highest_contiguous_sequence }) : null),
    [q.data],
  );

  // Verify the replay against every snapshot, in sequence order (docs/47 §3.3 step 4)
  const [checks, setChecks] = useState<Record<string, Verification>>({});
  const [contents, setContents] = useState<Record<string, string>>({});
  const [checkError, setCheckError] = useState<unknown>(null);
  useEffect(() => {
    if (!replay) return;
    let cancelled = false;
    setChecks({});
    (async () => {
      for (const point of replay.snapshotPoints()) {
        const snap = await cachedSnapshot(classId, studentId, sessionId, point.snapshotId);
        if (cancelled) return;
        if (!snap.content_available || snap.source_code == null) continue;
        const v = replay.verify(point, snap.source_code);
        setContents((c) => ({ ...c, [point.snapshotId]: snap.source_code! }));
        setChecks((c) => ({ ...c, [point.snapshotId]: v }));
      }
    })().catch((e) => !cancelled && setCheckError(e));
    return () => {
      cancelled = true;
    };
  }, [replay, classId, studentId, sessionId]);

  const last = replay?.lastSequence ?? 0;
  const [pos, setPos] = useState<number | null>(null);
  const at = Math.min(pos ?? last, last);
  const [compare, setCompare] = useState(false);
  const points = replay?.snapshotPoints() ?? [];
  const pointHere: SnapshotPoint | undefined = points.find((p) => p.sequence === at);
  const code = useMemo(() => replay?.codeAt(at) ?? "", [replay, at, checks]); // eslint-disable-line react-hooks/exhaustive-deps

  if (q.isPending) {
    return (
      <Group>
        <Loader size="sm" />
        {progress && <Text size="sm">{tt.session.loading(progress[0], progress[1])}</Text>}
      </Group>
    );
  }
  if (!timeline || !replay) return <ErrorAlert error={q.error} />;
  const s = timeline.session;
  const nearby = events.slice(Math.max(0, at - 40), at + 40);
  const verified = Object.values(checks);

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <Box>
          <Text size="xs" fw={700} c="indigo" tt="uppercase" lts="0.1em">Phát lại phiên làm bài</Text>
          <Title order={2} mt={4}>{s.problem_title}</Title>
          <Text size="sm" c="dimmed">
            {tt.context[s.context] ?? s.context} · {tt.student.opened} {fmt(s.opened_at)} · {tt.session.firstCode} {fmt(s.first_code_at)} · {tt.student.ended}{" "}
            {fmt(s.ended_at)}
            {s.working_time_seconds != null ? ` · ${tt.session.workingTime} ${Math.round(s.working_time_seconds / 60)} phút` : ""}
            {s.final_loc != null ? ` · ${tt.session.finalLoc} ${s.final_loc}` : ""}
          </Text>
        </Box>
        <Group>
          <Badge variant="light" color={s.status === "ACTIVE" ? "green" : "gray"}>
            {tt.sessionStatus[s.status] ?? s.status}
          </Badge>
          <LiveBadge />
          <Button component={Link} to={`/teacher/classes/${classId}/students/${studentId}`} variant="subtle" size="xs">
            {tt.session.back}
          </Button>
        </Group>
      </Group>
      {s.trace_purged_at && <Alert color="gray">{tt.session.purged}</Alert>}
      {replay.gapAfter !== null && <Alert color="yellow">{tt.session.gap(replay.gapAfter)}</Alert>}
      <ErrorAlert error={checkError} />

      <Grid gutter="xl" align="flex-start">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Paper className="surface-card" p={{ base: "md", sm: "lg" }}><Stack gap="md">
            <Group justify="space-between">
              <Text size="sm" data-testid="replay-position" data-sequence={at}>
                {tt.session.position(at, last)}
              </Text>
              <Group gap="xs">
                {verified.length > 0 && (
                  <Badge color={verified.every((v) => v.status === "match") ? "green" : "orange"} data-testid="replay-verification" data-checked={verified.length} data-mismatch={verified.filter((v) => v.status === "mismatch").length}>
                    {verified.filter((v) => v.status === "match").length}/{verified.length} {tt.session.match}
                  </Badge>
                )}
                {pointHere && contents[pointHere.snapshotId] !== undefined && (
                  <Switch size="xs" label={`${tt.session.snapshot} ↔ ${tt.session.replayed}`} checked={compare} onChange={(e) => setCompare(e.currentTarget.checked)} />
                )}
              </Group>
            </Group>
            <Group gap={4}>
              <Button size="compact-xs" variant="default" onClick={() => setPos(0)}>
                ⏮
              </Button>
              <Button size="compact-xs" variant="default" onClick={() => setPos(Math.max(0, at - 1))}>
                ◀
              </Button>
              <Button size="compact-xs" variant="default" onClick={() => setPos(Math.min(last, at + 1))}>
                ▶
              </Button>
              <Button size="compact-xs" variant="default" onClick={() => setPos(null)}>
                ⏭
              </Button>
              <Slider style={{ flex: 1 }} min={0} max={Math.max(1, last)} value={at} onChange={setPos} label={(v) => `#${v}`} />
            </Group>
            {pointHere && checks[pointHere.snapshotId] && (
              <Badge color={checks[pointHere.snapshotId]!.status === "match" ? "green" : "orange"} data-testid="point-verification" data-status={checks[pointHere.snapshotId]!.status}>
                {checks[pointHere.snapshotId]!.status === "match" ? `✓ ${tt.session.match}` : tt.session.mismatch}
              </Badge>
            )}
            <Paper withBorder style={{ overflow: "hidden" }}>
              {compare && pointHere && contents[pointHere.snapshotId] !== undefined ? (
                <DiffEditor height="380px" language={MONACO_LANGUAGE[timelineLanguage(events)] ?? "plaintext"} original={contents[pointHere.snapshotId]} modified={code} options={{ readOnly: true, minimap: { enabled: false } }} />
              ) : (
                <Editor height="380px" language={MONACO_LANGUAGE[timelineLanguage(events)] ?? "plaintext"} value={code} options={{ readOnly: true, minimap: { enabled: false }, scrollBeyondLastLine: false }} />
              )}
            </Paper>
            <Group justify="space-between"><Title order={5}>{tt.session.events}</Title><Badge variant="light" color="gray">{events.length} sự kiện</Badge></Group>
            <ScrollArea h={260} type="always">
              <Table verticalSpacing="xs" data-testid="event-list" highlightOnHover>
                <Table.Tbody>
                  {nearby.length === 0 && (
                    <Table.Tr>
                      <Table.Td>{tt.session.noEvents}</Table.Td>
                    </Table.Tr>
                  )}
                  {nearby.map((e) => (
                    <Table.Tr key={e.sequence_number} bg={e.sequence_number === at ? "var(--mantine-color-blue-light)" : undefined} style={{ cursor: "pointer" }} onClick={() => setPos(e.sequence_number)}>
                      <Table.Td w={60}>#{e.sequence_number}</Table.Td>
                      <Table.Td w={90}>{fmtTime(e.server_timestamp)}</Table.Td>
                      <Table.Td>{describe(e)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </Stack></Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Paper className="surface-card" p="lg"><Stack>
            <Title order={5}>{tt.session.snapshot}</Title>
            <Group gap={4}>
              {points.map((p) => (
                <Badge
                  key={p.snapshotId}
                  style={{ cursor: "pointer" }}
                  variant={p.sequence === at ? "filled" : "light"}
                  color={checks[p.snapshotId]?.status === "mismatch" ? "orange" : checks[p.snapshotId] ? "green" : "gray"}
                  onClick={() => setPos(p.sequence)}
                  data-testid="snapshot-marker"
                  data-event-type={p.eventType}
                  data-sequence={p.sequence}
                >
                  #{p.sequence} {tt.eventType[p.eventType] ?? p.eventType}
                </Badge>
              ))}
            </Group>
            <Title order={5}>{tt.session.runs}</Title>
            {timeline.runs.length === 0 && <Text size="sm" c="dimmed">—</Text>}
            {timeline.runs.map((r) => {
              const ev = events.find((e) => e.event_type === "RUN_REQUESTED" && e.payload.run_id === r.id);
              return (
                <Group key={r.id} gap="xs" data-testid="run-item" data-status={r.status}>
                  <Badge variant="light" color={r.verdict === "ACCEPTED" ? "green" : "red"}>
                    {r.verdict ? (t.verdicts[r.verdict] ?? r.verdict) : r.status}
                  </Badge>
                  <Text size="xs">{fmtTime(r.created_at)}</Text>
                  {ev && (
                    <Button size="compact-xs" variant="subtle" onClick={() => setPos(ev.sequence_number)}>
                      {tt.session.goTo}
                    </Button>
                  )}
                </Group>
              );
            })}
            <Title order={5}>{tt.student.signals}</Title>
            {timeline.signals.length === 0 && <Text size="sm" c="dimmed">{tt.student.noSignals}</Text>}
            {timeline.signals.map((sig) => (
              <SignalCard
                key={sig.id}
                classId={classId}
                signal={sig}
                onGoTo={(x) => {
                  const seq = signalSequence(events, x);
                  if (seq !== null) setPos(Math.min(seq, last));
                }}
              />
            ))}
            <Annotations studentId={studentId} sessionId={sessionId} signals={timeline.signals} />
          </Stack></Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

/** Language of the session from PROBLEM_OPENED (the session row carries it too, via the timeline). */
function timelineLanguage(events: ReplayEvent[]): string {
  const opened = events.find((e) => e.event_type === "PROBLEM_OPENED");
  return typeof opened?.payload.language === "string" ? opened.payload.language : "";
}
