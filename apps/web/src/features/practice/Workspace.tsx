import { Alert, Badge, Button, Code, Group, Loader, Paper, Stack, Text, Textarea, Title } from "@mantine/core";
import Editor, { type OnMount } from "@monaco-editor/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/errors";
import { traceTransport } from "../../api/traceTransport";
import { t } from "../../i18n/vi";
import {
  acquireSessionLock,
  checkpointPayload,
  editorChangedPayloads,
  problemOpenedPayload,
  runCompletedPayload,
  runRequestedPayload,
  TraceRecorder,
  type InputSource,
  type RecorderStatus,
} from "../../trace";
import { ErrorAlert } from "../../ui/ErrorAlert";
import * as P from "./practiceApi";
import { getTraceStore } from "./traceStore";

const MONACO_LANGUAGE: Record<string, string> = { CPP17: "cpp", PYTHON3: "python" };
const DRAFT_THROTTLE_MS = 1000;

interface Props {
  session: P.Session;
  userId: string;
  initialContent: string;
  /** The session is over on the server (submitted or ended). */
  onClosed(): void;
}

async function acquireWithRetry(sessionId: string) {
  // A lock released by an unmounting component is freed asynchronously (StrictMode remounts)
  for (let i = 0; i < 5; i++) {
    const release = await acquireSessionLock(sessionId);
    if (release) return release;
    await new Promise((r) => setTimeout(r, 150));
  }
  return null;
}

function RunOutput({ run }: { run: P.Run }) {
  const r = (run.testcase_results ?? {}) as Record<string, unknown>;
  const fields = ["stdout", "stderr", "compile_error_message", "runtime_error_message"].filter((k) => typeof r[k] === "string" && r[k]);
  return (
    <Stack gap={4} data-testid="run-result">
      <Group gap="xs">
        <Badge>{run.status}</Badge>
        {run.verdict && <Badge color={run.verdict === "ACCEPTED" ? "green" : "red"}>{t.verdicts[run.verdict] ?? run.verdict}</Badge>}
        {run.execution_time_ms != null && (
          <Text size="sm">
            {t.problem.time}: {run.execution_time_ms} ms
          </Text>
        )}
      </Group>
      {fields.map((k) => (
        <div key={k}>
          <Text size="xs" c="dimmed">
            {k}
          </Text>
          <Code block>{String(r[k])}</Code>
        </div>
      ))}
    </Stack>
  );
}

function SubmissionResult({ submission }: { submission: P.Submission }) {
  if (!submission.result_visible) return <Text>{t.problem.resultHidden}</Text>;
  const summary = (submission.judge_result ?? {}) as Record<string, unknown>;
  return (
    <Stack gap={4} data-testid="submission-result" data-verdict={submission.verdict ?? ""}>
      <Group gap="xs">
        <Badge>{submission.status}</Badge>
        {submission.verdict && (
          <Badge color={submission.verdict === "ACCEPTED" ? "green" : "red"} size="lg">
            {t.verdicts[submission.verdict] ?? submission.verdict}
          </Badge>
        )}
        {submission.score != null && (
          <Text>
            {t.problem.score}: {submission.score}
          </Text>
        )}
        {typeof summary.passed_count === "number" && (
          <Text size="sm">
            {String(summary.passed_count)}/{String(summary.total_count)}
          </Text>
        )}
      </Group>
      {typeof summary.compile_error_message === "string" && summary.compile_error_message && <Code block>{summary.compile_error_message}</Code>}
    </Stack>
  );
}

/** Editor + trace capture + run/submit for one ACTIVE session (docs/46 §3.6). */
export function Workspace({ session, userId, initialContent, onClosed }: Props) {
  const [recorder, setRecorder] = useState<TraceRecorder | null>(null);
  const [status, setStatus] = useState<RecorderStatus | null>(null);
  const [otherTab, setOtherTab] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [stdin, setStdin] = useState("");
  const [busy, setBusy] = useState<"run" | "submit" | "end" | null>(null);
  const [run, setRun] = useState<P.Run | null>(null);
  const [submission, setSubmission] = useState<P.Submission | null>(null);
  const [closed, setClosed] = useState(false);

  const recRef = useRef<TraceRecorder | null>(null);
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const pasteRef = useRef(false);
  const draftTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSnapshotContent = useRef(initialContent);

  // Recorder lifecycle: single writer lock, open, PROBLEM_OPENED on a fresh session
  useEffect(() => {
    let cancelled = false;
    let release: (() => void) | null = null;
    let rec: TraceRecorder | null = null;
    (async () => {
      release = await acquireWithRetry(session.id);
      if (cancelled) return release?.();
      if (!release) return setOtherTab(true);
      rec = await TraceRecorder.open({
        sessionId: session.id,
        userId,
        problemId: session.problem_id,
        language: session.language,
        store: await getTraceStore(),
        transport: traceTransport,
        onStatus: setStatus,
      });
      if (cancelled) return rec.dispose();
      if (rec.lastSequence === 0) rec.record("PROBLEM_OPENED", problemOpenedPayload(session.problem_id, session.language));
      recRef.current = rec;
      setRecorder(rec);
    })().catch(setError);
    return () => {
      cancelled = true;
      rec?.dispose();
      recRef.current = null;
      release?.();
    };
  }, [session.id, session.problem_id, session.language, userId]);

  // Network and page lifecycle: retry when back online, flush when hidden, beacon on close
  useEffect(() => {
    if (!recorder) return;
    const online = () => recorder.kick();
    const hidden = () => {
      if (document.visibilityState === "hidden") recorder.kick();
    };
    const pagehide = () => recorder.beacon();
    window.addEventListener("online", online);
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("pagehide", pagehide);
    return () => {
      window.removeEventListener("online", online);
      document.removeEventListener("visibilitychange", hidden);
      window.removeEventListener("pagehide", pagehide);
    };
  }, [recorder]);

  // Periodic CHECKPOINT snapshot when the code changed (REQ-TRACE-013)
  useEffect(() => {
    if (!recorder || closed) return;
    const id = setInterval(async () => {
      const content = editorRef.current?.getValue();
      if (content === undefined || content === lastSnapshotContent.current || recorder.stopped) return;
      try {
        const snap = await P.createSnapshot(session.id, "CHECKPOINT", session.language, content);
        lastSnapshotContent.current = content;
        recorder.record("SESSION_CHECKPOINT", checkpointPayload(snap.id));
      } catch {
        // Skipped; the next interval tries again (docs/46 §3.6)
      }
    }, recorder.checkpointIntervalSeconds * 1000);
    return () => clearInterval(id);
  }, [recorder, closed, session.id, session.language]);

  const saveDraft = useCallback(() => {
    if (draftTimer.current) return;
    draftTimer.current = setTimeout(async () => {
      draftTimer.current = null;
      const content = editorRef.current?.getValue();
      if (content === undefined) return;
      await (await getTraceStore()).putDraft({ session_id: session.id, user_id: userId, content, updated_at: new Date().toISOString() });
    }, DRAFT_THROTTLE_MS);
  }, [session.id, userId]);

  const onMount: OnMount = (editor) => {
    editorRef.current = editor;
    editor.getDomNode()?.addEventListener("paste", () => (pasteRef.current = true), true);
    editor.onDidChangeModelContent((e) => {
      if (e.isFlush) return;
      const source: InputSource = pasteRef.current ? "paste" : e.isUndoing || e.isRedoing ? "other" : "typing";
      pasteRef.current = false;
      const rec = recRef.current;
      if (!rec) return;
      for (const payload of editorChangedPayloads(e.changes, e.versionId, source)) rec.record("EDITOR_CHANGED", payload);
      saveDraft();
    });
  };

  const flushOrExplain = async (rec: TraceRecorder): Promise<number> => {
    try {
      return await rec.flush();
    } catch {
      throw new ApiError(null, "TRACE_NOT_FLUSHED", t.problem.flushFailed, "");
    }
  };

  const doRun = async () => {
    const rec = recorder;
    const content = editorRef.current?.getValue();
    if (!rec || content === undefined) return;
    setBusy("run");
    setError(null);
    setRun(null);
    try {
      const snap = await P.createSnapshot(session.id, "RUN", session.language, content);
      lastSnapshotContent.current = content;
      const created = await P.createRun(session.id, snap.id, stdin);
      rec.record("RUN_REQUESTED", runRequestedPayload(snap.id, created.id, stdin));
      setRun(created);
      const done = await P.poll(() => P.getRun(session.id, created.id), (r) => P.isFinished(r.status), 1000, 60_000);
      rec.record("RUN_COMPLETED", runCompletedPayload(done));
      setRun(done);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  };

  const doSubmit = async () => {
    const rec = recorder;
    const content = editorRef.current?.getValue();
    if (!rec || content === undefined || !window.confirm(t.problem.submitConfirm)) return;
    setBusy("submit");
    setError(null);
    editorRef.current?.updateOptions({ readOnly: true });
    try {
      await flushOrExplain(rec); // F9: submit has no flush guard on the server
      const snap = await P.createSnapshot(session.id, "SUBMIT", session.language, content);
      const created = await P.submit(session.id, snap.id);
      setClosed(true);
      await rec.finish();
      setSubmission(created);
      setSubmission(await P.poll(() => P.getSubmission(created.id), (s) => P.isFinished(s.status), 2000, 120_000));
    } catch (err) {
      setError(err);
      if (!rec.stopped) editorRef.current?.updateOptions({ readOnly: false });
    } finally {
      setBusy(null);
    }
  };

  const doEnd = async () => {
    const rec = recorder;
    if (!rec || !window.confirm(t.problem.endConfirm)) return;
    setBusy("end");
    setError(null);
    try {
      await flushOrExplain(rec);
      await P.endSession(session.id, rec.lastSequence);
      setClosed(true);
      await rec.finish();
      onClosed();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  };

  if (otherTab) return <Alert color="yellow">{t.problem.otherTab}</Alert>;

  const phase = status?.phase ?? "idle";
  return (
    <Stack>
      <Group justify="space-between">
        <Badge
          variant="light"
          color={phase === "idle" ? "green" : phase === "sending" ? "blue" : phase === "retrying" ? "yellow" : "red"}
          data-testid="trace-status"
          data-phase={phase}
          data-pending={status?.pending ?? 0}
        >
          {t.trace[phase]}
          {status && status.pending > 0 ? ` · ${t.trace.pending(status.pending)}` : ""}
        </Badge>
        {!closed && (
          <Group>
            <Button onClick={() => void doRun()} loading={busy === "run"} disabled={!recorder || busy !== null}>
              {t.problem.run}
            </Button>
            <Button color="green" onClick={() => void doSubmit()} loading={busy === "submit"} disabled={!recorder || busy !== null}>
              {t.problem.submit}
            </Button>
            <Button variant="default" onClick={() => void doEnd()} loading={busy === "end"} disabled={!recorder || busy !== null}>
              {t.problem.end}
            </Button>
          </Group>
        )}
      </Group>
      {status?.error && (phase === "failed" || phase === "closed" || phase === "auth") && <ErrorAlert error={status.error} />}
      <Paper withBorder data-testid="editor">
        <Editor
          height="420px"
          language={MONACO_LANGUAGE[session.language] ?? "plaintext"}
          defaultValue={initialContent}
          onMount={onMount}
          loading={<Loader />}
          options={{ minimap: { enabled: false }, readOnly: !recorder || closed, fontSize: 14, scrollBeyondLastLine: false, automaticLayout: true }}
        />
      </Paper>
      <ErrorAlert error={error} />
      {!closed && <Textarea label={t.problem.stdin} value={stdin} onChange={(e) => setStdin(e.currentTarget.value)} autosize minRows={2} />}
      {run && (
        <Paper withBorder p="sm">
          <Title order={5} mb="xs">
            {t.problem.runResult}
          </Title>
          {P.isFinished(run.status) ? <RunOutput run={run} /> : <Text>{t.problem.running}</Text>}
        </Paper>
      )}
      {submission && (
        <Paper withBorder p="sm">
          <Title order={5} mb="xs">
            {t.problem.submitResult}
          </Title>
          {P.isFinished(submission.status) ? <SubmissionResult submission={submission} /> : <Text>{t.problem.judging}</Text>}
          <Button mt="sm" variant="light" onClick={onClosed}>
            {t.problem.newAttempt}
          </Button>
        </Paper>
      )}
    </Stack>
  );
}
