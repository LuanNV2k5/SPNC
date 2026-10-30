import { Badge, Box, Button, Center, Group, Loader, Pagination, Paper, Select, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { difficultyLabel, languageLabel, tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { deleteProblem, listProblems, problemKeys, type ProblemFilters } from "./problemApi";

const PAGE_SIZE = 20;

export function ProblemsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [difficulty, setDifficulty] = useState<ProblemFilters["difficulty"]>();
  const [language, setLanguage] = useState<ProblemFilters["language"]>();
  const [visibility, setVisibility] = useState<ProblemFilters["visibility"]>();
  const filters = { page, difficulty, language, visibility };
  const query = useQuery({ queryKey: problemKeys.list(filters), queryFn: () => listProblems(filters) });
  const remove = useMutation({
    mutationFn: deleteProblem,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["t", "problems"] }),
  });
  const resetPage = () => setPage(1);
  const activeFilters = [difficulty, language, visibility].filter(Boolean).length;

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <Box>
          <Text size="xs" fw={700} c="indigo" tt="uppercase" lts="0.1em">Không gian giảng viên</Text>
          <Title order={2} mt={4}>{tt.problems.title}</Title>
          <Text c="dimmed" mt={6}>Soạn nội dung, quản lý bộ kiểm thử và phát hành bài tập cho từng lớp.</Text>
        </Box>
        <Button component={Link} to="/teacher/problems/new" size="md">+ {tt.problems.create}</Button>
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        <Paper className="surface-card metric-card" p="lg"><Text size="xs" c="dimmed" fw={600} tt="uppercase">Tổng đề bài</Text><Text fz={28} fw={750} mt={4}>{query.data?.total ?? "—"}</Text><Text size="xs" c="dimmed">Trong kho đề của bạn</Text></Paper>
        <Paper className="surface-card metric-card" p="lg"><Text size="xs" c="dimmed" fw={600} tt="uppercase">Đang hiển thị</Text><Text fz={28} fw={750} mt={4}>{query.data?.items.length ?? "—"}</Text><Text size="xs" c="dimmed">Kết quả trên trang này</Text></Paper>
        <Paper className="surface-card metric-card" p="lg"><Text size="xs" c="dimmed" fw={600} tt="uppercase">Bộ lọc</Text><Text fz={28} fw={750} mt={4}>{activeFilters}</Text><Text size="xs" c="dimmed">Tiêu chí đang áp dụng</Text></Paper>
      </SimpleGrid>

      <Paper className="surface-card" p="lg">
        <Group justify="space-between" mb="md"><Box><Text fw={700}>Tìm trong kho đề</Text><Text size="sm" c="dimmed">Thu hẹp danh sách theo thông tin bài tập.</Text></Box>{activeFilters > 0 && <Button variant="subtle" size="xs" onClick={() => { setDifficulty(undefined); setLanguage(undefined); setVisibility(undefined); resetPage(); }}>Xóa bộ lọc</Button>}</Group>
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <Select label={tt.problems.fields.difficulty} placeholder={tt.problems.all} clearable value={difficulty ?? null} onChange={(value) => { setDifficulty((value ?? undefined) as ProblemFilters["difficulty"]); resetPage(); }} data={Object.entries(difficultyLabel).map(([value, label]) => ({ value, label }))} />
          <Select label={tt.problems.fields.language} placeholder={tt.problems.all} clearable value={language ?? null} onChange={(value) => { setLanguage((value ?? undefined) as ProblemFilters["language"]); resetPage(); }} data={Object.entries(languageLabel).map(([value, label]) => ({ value, label }))} />
          <Select label={tt.problems.fields.visibility} placeholder={tt.problems.all} clearable value={visibility ?? null} onChange={(value) => { setVisibility((value ?? undefined) as ProblemFilters["visibility"]); resetPage(); }} data={Object.entries(tt.problems.visibility).map(([value, label]) => ({ value, label }))} />
        </SimpleGrid>
      </Paper>
      {query.isPending && <Center py="xl"><Loader /></Center>}
      <ErrorAlert error={query.error ?? remove.error} />
      {query.data?.items.length === 0 && <Paper className="surface-card" p={48}><Center><Stack align="center" gap="xs"><Text fz={36}>◇</Text><Text fw={700}>{tt.problems.empty}</Text><Text size="sm" c="dimmed" ta="center">Tạo đề đầu tiên để bắt đầu xây dựng kho học liệu của lớp.</Text><Button component={Link} to="/teacher/problems/new" mt="sm">{tt.problems.create}</Button></Stack></Center></Paper>}
      {!!query.data?.items.length && (
        <Paper className="surface-card" style={{ overflow: "hidden" }}>
          <Box px="lg" py="md"><Text fw={700}>Danh sách đề bài</Text><Text size="sm" c="dimmed">Cập nhật lần lượt nội dung, testcase và phạm vi phát hành.</Text></Box>
          <Table.ScrollContainer minWidth={760}>
            <Table highlightOnHover verticalSpacing="md" horizontalSpacing="lg" data-testid="teacher-problem-table">
              <Table.Thead bg="gray.0"><Table.Tr><Table.Th>{tt.problems.fields.title}</Table.Th><Table.Th>{tt.problems.fields.difficulty}</Table.Th><Table.Th>{tt.problems.fields.visibility}</Table.Th><Table.Th>{tt.problems.fields.language}</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {query.data.items.map((problem) => (
                  <Table.Tr key={problem.id}>
                    <Table.Td><Text fw={650}>{problem.title}</Text><Text size="xs" c="dimmed" mt={3}>Cập nhật {new Date(problem.updated_at).toLocaleDateString("vi-VN")}</Text></Table.Td>
                    <Table.Td>{problem.difficulty ? <Badge variant="light" color={problem.difficulty === "HARD" ? "red" : problem.difficulty === "MEDIUM" ? "yellow" : "teal"}>{difficultyLabel[problem.difficulty] ?? problem.difficulty}</Badge> : <Text c="dimmed">—</Text>}</Table.Td>
                    <Table.Td><Badge variant="dot" color={problem.visibility === "PUBLIC" ? "teal" : problem.visibility === "CLASS" ? "blue" : "gray"}>{tt.problems.visibility[problem.visibility as keyof typeof tt.problems.visibility] ?? problem.visibility}</Badge></Table.Td>
                    <Table.Td><Group gap={5}>{problem.supported_languages.map((item) => <Badge key={item} size="sm" color="gray" variant="light">{languageLabel[item] ?? item}</Badge>)}</Group></Table.Td>
                    <Table.Td><Group gap="xs" justify="flex-end" wrap="nowrap"><Button component={Link} to={`/teacher/problems/${problem.id}`} size="compact-sm" variant="light">{tt.problems.actions.edit}</Button><Button size="compact-sm" color="red" variant="subtle" loading={remove.isPending} onClick={() => window.confirm(tt.problems.deleteConfirm) && remove.mutate(problem.id)}>{tt.problems.actions.delete}</Button></Group></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}
      {query.data && query.data.total > PAGE_SIZE && <Group justify="center"><Pagination total={Math.ceil(query.data.total / PAGE_SIZE)} value={page} onChange={setPage} /></Group>}
    </Stack>
  );
}
