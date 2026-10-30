import { Badge, Box, Button, Center, Code, Grid, Group, Loader, Paper, SegmentedControl, Stack, Text, Title, TypographyStylesProvider } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { difficultyLabel, languageLabel, t } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { useAuth } from "../auth/AuthContext";
import * as P from "./practiceApi";
import { getTraceStore } from "./traceStore";
import { Workspace } from "./Workspace";

type View = { kind: "loading" } | { kind: "choose" } | { kind: "active"; session: P.Session; content: string };

/**
 * The statement is shown only once a session is open (docs/47 D7): `opened_at` is then the moment
 * the student first sees it, which is the baseline FAST_FIRST_CODE measures from.
 */
function Statement({ problem, full }: { problem: P.Problem; full: boolean }) {
  const samples = useQuery({ queryKey: ["samples", problem.id], queryFn: () => P.getSamples(problem.id), enabled: full });
  const section = (label: string, text?: string | null) =>
    text ? (
      <div>
        <Text fw={600}>{label}</Text>
        <Text style={{ whiteSpace: "pre-wrap" }}>{text}</Text>
      </div>
    ) : null;
  return (
    <Stack gap="lg">
      <Group>
        <Title order={3} data-testid="problem-title">
          {problem.title}
        </Title>
        {problem.difficulty && <Badge variant="light">{difficultyLabel[problem.difficulty] ?? problem.difficulty}</Badge>}
      </Group>
      <Group gap="xs"><Badge variant="outline" color="gray">{problem.time_limit_ms} ms</Badge><Badge variant="outline" color="gray">{problem.memory_limit_mb} MB</Badge></Group>
      <Text size="sm" c="dimmed" style={{ display: "none" }}>
        {t.problem.timeLimit}: {problem.time_limit_ms} ms · {t.problem.memoryLimit}: {problem.memory_limit_mb} MB
      </Text>
      {!full && <Text c="dimmed">{t.problem.statementAfterStart}</Text>}
      {full && (
        <TypographyStylesProvider>
          <Text style={{ whiteSpace: "pre-wrap" }} data-testid="problem-statement">
            {problem.description}
          </Text>
        </TypographyStylesProvider>
      )}
      {full && <Box p="md" bg="gray.0" style={{ borderRadius: 10 }}>{section(t.problem.input, problem.input_format)}</Box>}
      {full && <Box p="md" bg="gray.0" style={{ borderRadius: 10 }}>{section(t.problem.output, problem.output_format)}</Box>}
      {full && <Box p="md" bg="gray.0" style={{ borderRadius: 10 }}>{section(t.problem.constraints, problem.constraints)}</Box>}
      {full && samples.data && samples.data.items.length > 0 && (
        <div>
          <Text fw={600}>{t.problem.samples}</Text>
          {samples.data.items.map((s) => (
            <Grid key={s.order_index} gutter="xs">
              <Grid.Col span={6}>
                <Code block>{s.input_data}</Code>
              </Grid.Col>
              <Grid.Col span={6}>
                <Code block>{s.expected_output}</Code>
              </Grid.Col>
            </Grid>
          ))}
        </div>
      )}
    </Stack>
  );
}

export function ProblemPage() {
  const { problemId = "" } = useParams();
  const { user } = useAuth();
  const problem = useQuery({ queryKey: ["problem", problemId], queryFn: () => P.getProblem(problemId) });
  const [view, setView] = useState<View>({ kind: "loading" });
  const [language, setLanguage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [starting, setStarting] = useState(false);

  // docs/46 D10: resume only a session this browser holds data for; otherwise close it cleanly
  const resolve = useCallback(async () => {
    setView({ kind: "loading" });
    try {
      const active = await P.findActiveSession(problemId);
      if (active) {
        const store = await getTraceStore();
        const [meta, draft] = await Promise.all([store.getMeta(active.id), store.getDraft(active.id)]);
        if (meta || draft) {
          setView({ kind: "active", session: active, content: draft?.content ?? "" });
          return;
        }
        await P.endSession(active.id).catch(() => undefined);
      }
      setView({ kind: "choose" });
    } catch (err) {
      setError(err);
      setView({ kind: "choose" });
    }
  }, [problemId]);

  useEffect(() => {
    void resolve();
  }, [resolve]);

  const languages = problem.data?.supported_languages ?? [];
  const chosen = language ?? languages[0] ?? null;

  const start = async () => {
    if (!chosen) return;
    setStarting(true);
    setError(null);
    try {
      const session = await P.startSession(problemId, chosen);
      setView({ kind: "active", session, content: "" });
    } catch (err) {
      setError(err);
    } finally {
      setStarting(false);
    }
  };

  if (problem.isPending) return <Center py={80}><Loader /></Center>;
  if (problem.error || !problem.data || !user) {
    return (
      <Stack>
        <ErrorAlert error={problem.error} />
        <Button component={Link} to="/practice" variant="subtle">
          {t.problem.backToList}
        </Button>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <Button component={Link} to="/practice" variant="subtle" size="compact-sm" w="fit-content">← {t.problem.backToList}</Button>
    <Grid gutter="xl" align="flex-start">
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Paper className="surface-card" p={{ base: "md", sm: "xl" }} style={{ position: "sticky", top: 88 }}>
          <Statement problem={problem.data} full={view.kind === "active"} />
        </Paper>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 7 }}>
        <ErrorAlert error={error} />
        {view.kind === "loading" && <Loader />}
        {view.kind === "choose" && (
          <Paper className="surface-card" p={{ base: "lg", sm: 32 }}><Stack align="flex-start">
            <Box><Title order={4}>Bắt đầu phiên làm bài</Title><Text c="dimmed" size="sm" mt={5}>{t.problem.chooseLanguage}</Text></Box>
            <SegmentedControl value={chosen ?? ""} onChange={setLanguage} data={languages.map((l) => ({ value: l, label: languageLabel[l] ?? l }))} />
            <Button onClick={() => void start()} loading={starting} data-testid="start-session" size="md">
              {t.problem.start}
            </Button>
          </Stack></Paper>
        )}
        {view.kind === "active" && (
          <Workspace key={view.session.id} session={view.session} userId={user.id} initialContent={view.content} onClosed={() => void resolve()} />
        )}
      </Grid.Col>
    </Grid></Stack>
  );
}
