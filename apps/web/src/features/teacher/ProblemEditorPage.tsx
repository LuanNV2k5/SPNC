import { Badge, Box, Button, Center, Group, Loader, Paper, Stack, Tabs, Text, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";
import { tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { ProblemForm } from "./ProblemForm";
import { PublicationsPanel } from "./PublicationsPanel";
import { TestCasesPanel } from "./TestCasesPanel";
import { createProblem, deleteProblem, getProblem, problemKeys, updateProblem } from "./problemApi";
import { draftFromProblem, emptyProblemDraft, problemBody, type ProblemDraft } from "./problemDraft";

export function ProblemEditorPage() {
  const { problemId } = useParams();
  const editing = Boolean(problemId);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: problemKeys.detail(problemId ?? "new"), queryFn: () => getProblem(problemId!), enabled: editing });
  const save = useMutation({
    mutationFn: (draft: ProblemDraft) => editing ? updateProblem(problemId!, problemBody(draft)) : createProblem(problemBody(draft)),
    onSuccess: (problem) => {
      void qc.invalidateQueries({ queryKey: ["t", "problems"] });
      void qc.invalidateQueries({ queryKey: problemKeys.detail(problem.id) });
      if (!editing) navigate(`/teacher/problems/${problem.id}`, { replace: true });
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteProblem(problemId!),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["t", "problems"] }); navigate("/teacher/problems", { replace: true }); },
  });

  if (editing && query.isPending) return <Center py={80}><Loader /></Center>;
  if (editing && !query.data) return <ErrorAlert error={query.error} />;
  const problem = query.data;
  const initial = problem ? draftFromProblem(problem) : emptyProblemDraft();

  return (
    <Stack gap="xl">
      <Box>
        <Button component={Link} to="/teacher/problems" variant="subtle" size="compact-sm" mb="md">← {tt.problems.back}</Button>
        <Group justify="space-between" align="flex-start">
          <Box>
            <Group gap="sm"><Title order={2}>{problem ? problem.title : tt.problems.create}</Title>{problem && <Badge variant="dot" color={problem.visibility === "PUBLIC" ? "teal" : problem.visibility === "CLASS" ? "blue" : "gray"}>{tt.problems.visibility[problem.visibility as keyof typeof tt.problems.visibility]}</Badge>}</Group>
            <Text c="dimmed" mt={7}>{problem ? "Hoàn thiện nội dung, bộ kiểm thử và phân phối bài tập từ một nơi." : "Tạo khung đề bài trước; testcase và phát hành sẽ mở sau khi lưu."}</Text>
          </Box>
        {problem && <Button color="red" variant="light" loading={remove.isPending} onClick={() => window.confirm(tt.problems.deleteConfirm) && remove.mutate()}>{tt.problems.actions.delete}</Button>}
        </Group>
      </Box>
      <ErrorAlert error={save.error ?? remove.error} />
      {problem ? (
        <Tabs defaultValue="content" keepMounted={false} className="editor-tabs">
          <Tabs.List grow><Tabs.Tab value="content">1 · {tt.problems.tabs.content}</Tabs.Tab><Tabs.Tab value="tests">2 · {tt.problems.tabs.tests}</Tabs.Tab><Tabs.Tab value="publications">3 · {tt.problems.tabs.publications}</Tabs.Tab></Tabs.List>
          <Tabs.Panel value="content" pt="xl"><ProblemForm key={problem.updated_at} initial={initial} submitLabel={tt.problems.actions.save} pending={save.isPending} onSubmit={(draft) => save.mutate(draft)} /></Tabs.Panel>
          <Tabs.Panel value="tests" pt="xl"><Paper className="surface-card" p={{ base: "md", sm: "xl" }}><TestCasesPanel problemId={problem.id} /></Paper></Tabs.Panel>
          <Tabs.Panel value="publications" pt="xl"><Paper className="surface-card" p={{ base: "md", sm: "xl" }}><PublicationsPanel problem={problem} /></Paper></Tabs.Panel>
        </Tabs>
      ) : (
        <ProblemForm initial={initial} submitLabel={tt.problems.create} pending={save.isPending} onSubmit={(draft) => save.mutate(draft)} />
      )}
    </Stack>
  );
}
