import { Badge, Box, Button, Center, Grid, Group, Loader, NumberInput, Paper, SimpleGrid, Stack, Switch, Text, Textarea, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { createTestCase, deleteTestCase, listTestCases, problemKeys, type TestCase, updateTestCase } from "./problemApi";

interface Draft {
  input: string;
  expected: string;
  sample: boolean;
  weight: number;
}

const empty = (): Draft => ({ input: "", expected: "", sample: false, weight: 10 });

function TestCaseItem({ problemId, item }: { problemId: string; item: TestCase }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>({ input: item.input_data, expected: item.expected_output, sample: item.is_sample, weight: item.score_weight });
  const refresh = () => void qc.invalidateQueries({ queryKey: problemKeys.testCases(problemId) });
  const update = useMutation({
    mutationFn: () => updateTestCase(problemId, item.id, { input_data: draft.input, expected_output: draft.expected, is_sample: draft.sample, score_weight: draft.weight }),
    onSuccess: () => { setEditing(false); refresh(); },
  });
  const remove = useMutation({ mutationFn: () => deleteTestCase(problemId, item.id), onSuccess: refresh });

  return (
    <Paper withBorder p="lg" data-testid="test-case-item" bg="white">
      <Stack gap="xs">
        <Group justify="space-between">
          <Group gap="xs">
            <Text fw={600}>#{item.order_index}</Text>
            <Badge variant="light" color={item.is_sample ? "blue" : "gray"}>{item.is_sample ? tt.problems.testCases.sample : tt.problems.testCases.hidden}</Badge>
            <Text size="sm" c="dimmed">{tt.problems.testCases.weight}: {item.score_weight}</Text>
          </Group>
          <Group gap="xs">
            <Button size="compact-xs" variant="subtle" onClick={() => setEditing((value) => !value)}>{editing ? tt.problems.actions.cancel : tt.problems.actions.edit}</Button>
            <Button size="compact-xs" variant="subtle" color="red" loading={remove.isPending} onClick={() => window.confirm(tt.problems.testCases.deleteConfirm) && remove.mutate()}>{tt.problems.actions.delete}</Button>
          </Group>
        </Group>
        {editing ? (
          <>
            <Textarea label={tt.problems.testCases.input} value={draft.input} onChange={(e) => setDraft({ ...draft, input: e.currentTarget.value })} autosize minRows={2} />
            <Textarea label={tt.problems.testCases.expected} value={draft.expected} onChange={(e) => setDraft({ ...draft, expected: e.currentTarget.value })} autosize minRows={2} required />
            <Group>
              <Switch label={tt.problems.testCases.isSample} checked={draft.sample} onChange={(e) => setDraft({ ...draft, sample: e.currentTarget.checked })} />
              <NumberInput label={tt.problems.testCases.weight} value={draft.weight} onChange={(value) => setDraft({ ...draft, weight: Number(value) || 0 })} min={0} w={140} />
            </Group>
            <Button size="xs" loading={update.isPending} onClick={() => update.mutate()} disabled={!draft.expected.trim()}>{tt.problems.actions.save}</Button>
          </>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Box><Text size="xs" c="dimmed" fw={650}>{tt.problems.testCases.input}</Text><Text component="pre" className="code-preview">{item.input_data || "∅"}</Text></Box>
            <Box><Text size="xs" c="dimmed" fw={650}>{tt.problems.testCases.expected}</Text><Text component="pre" className="code-preview">{item.expected_output}</Text></Box>
          </SimpleGrid>
        )}
        <ErrorAlert error={update.error ?? remove.error} />
      </Stack>
    </Paper>
  );
}

export function TestCasesPanel({ problemId }: { problemId: string }) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: problemKeys.testCases(problemId), queryFn: () => listTestCases(problemId) });
  const [draft, setDraft] = useState(empty);
  const create = useMutation({
    mutationFn: () => createTestCase(problemId, { input_data: draft.input, expected_output: draft.expected, is_sample: draft.sample, score_weight: draft.weight }),
    onSuccess: () => { setDraft(empty()); void qc.invalidateQueries({ queryKey: problemKeys.testCases(problemId) }); },
  });
  const submit = (event: FormEvent) => { event.preventDefault(); if (draft.expected.trim()) create.mutate(); };

  return (
    <Stack gap="xl">
      <Box>
        <Title order={4}>Bộ kiểm thử</Title>
        <Text size="sm" c="dimmed" mt={5}>Thêm ít nhất một testcase ví dụ để học sinh hiểu định dạng, sau đó bổ sung các trường hợp ẩn để chấm bài.</Text>
      </Box>
      <Paper withBorder p={{ base: "md", sm: "lg" }} bg="gray.0">
        <form onSubmit={submit}>
          <Stack>
            <Group justify="space-between"><Box><Text fw={700}>{tt.problems.testCases.add}</Text><Text size="xs" c="dimmed">Dữ liệu được so khớp chính xác khi chấm.</Text></Box><Badge variant="light" color={draft.sample ? "blue" : "gray"}>{draft.sample ? tt.problems.testCases.sample : tt.problems.testCases.hidden}</Badge></Group>
            <Grid>
              <Grid.Col span={{ base: 12, sm: 6 }}><Textarea name="test_input" label={tt.problems.testCases.input} placeholder="Ví dụ: 1 2" value={draft.input} onChange={(e) => setDraft({ ...draft, input: e.currentTarget.value })} autosize minRows={4} styles={{ input: { fontFamily: "monospace" } }} /></Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}><Textarea name="test_expected" label={tt.problems.testCases.expected} placeholder="Ví dụ: 3" value={draft.expected} onChange={(e) => setDraft({ ...draft, expected: e.currentTarget.value })} autosize minRows={4} required styles={{ input: { fontFamily: "monospace" } }} /></Grid.Col>
            </Grid>
            <Group align="flex-end" justify="space-between">
              <Group align="flex-end">
              <Switch label={tt.problems.testCases.isSample} checked={draft.sample} onChange={(e) => setDraft({ ...draft, sample: e.currentTarget.checked })} />
              <NumberInput label={tt.problems.testCases.weight} value={draft.weight} onChange={(value) => setDraft({ ...draft, weight: Number(value) || 0 })} min={0} w={140} />
              </Group>
              <Button type="submit" loading={create.isPending}>+ {tt.problems.testCases.add}</Button>
            </Group>
          </Stack>
        </form>
        <ErrorAlert error={create.error} />
      </Paper>
      {query.isPending && <Center py="xl"><Loader /></Center>}
      <ErrorAlert error={query.error} />
      {query.data?.items.length === 0 && <Center py="xl"><Stack align="center" gap={4}><Text fz={30}>⌁</Text><Text fw={650}>{tt.problems.testCases.empty}</Text><Text size="sm" c="dimmed">Testcase mới sẽ xuất hiện tại đây.</Text></Stack></Center>}
      {!!query.data?.items.length && <Group justify="space-between"><Text fw={700}>Danh sách testcase</Text><Badge variant="light">{query.data.items.length} testcase</Badge></Group>}
      {query.data?.items.map((item) => <TestCaseItem key={item.id} problemId={problemId} item={item} />)}
    </Stack>
  );
}
