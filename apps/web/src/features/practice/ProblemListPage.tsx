import { Badge, Box, Button, Center, Group, Loader, Pagination, Paper, Select, SimpleGrid, Stack, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, call } from "../../api/client";
import { difficultyLabel, languageLabel, t } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { PageHeader } from "../../ui/PageHeader";

const PAGE_SIZE = 20;
type Difficulty = "EASY" | "MEDIUM" | "HARD";
type Language = "CPP17" | "PYTHON3";

export function ProblemListPage() {
  const [page, setPage] = useState(1);
  const [difficulty, setDifficulty] = useState<Difficulty | null>(null);
  const [language, setLanguage] = useState<Language | null>(null);
  const q = useQuery({
    queryKey: ["practice-problems", page, difficulty, language],
    queryFn: () =>
      call(
        api.GET("/api/v1/my/practice/problems", {
          params: { query: { page, size: PAGE_SIZE, difficulty: difficulty ?? undefined, language: language ?? undefined } },
        }),
      ),
  });

  return (
    <Stack gap="xl">
      <PageHeader eyebrow="Không gian sinh viên" title={t.practice.title} description="Chọn bài phù hợp với trình độ và bắt đầu một phiên luyện tập mới." />
      <Paper className="surface-card" p="lg">
      <Group justify="space-between" mb="md"><Box><Text fw={700}>Bộ lọc bài tập</Text><Text size="sm" c="dimmed">Tìm bài theo độ khó và ngôn ngữ bạn muốn luyện.</Text></Box><Badge variant="light">{q.data?.total ?? 0} bài</Badge></Group>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <Select
          label={t.practice.difficulty}
          placeholder={t.practice.all}
          clearable
          value={difficulty}
          onChange={(v) => {
            setDifficulty(v as Difficulty | null);
            setPage(1);
          }}
          data={Object.entries(difficultyLabel).map(([value, label]) => ({ value, label }))}
        />
        <Select
          label={t.practice.language}
          placeholder={t.practice.all}
          clearable
          value={language}
          onChange={(v) => {
            setLanguage(v as Language | null);
            setPage(1);
          }}
          data={Object.entries(languageLabel).map(([value, label]) => ({ value, label }))}
        />
      </SimpleGrid>
      </Paper>
      {q.isPending && <Center py="xl"><Loader /></Center>}
      <ErrorAlert error={q.error} />
      {q.data && q.data.items.length === 0 && <Paper className="empty-panel" p={48}><Center><Stack align="center" gap={5}><Text fz={32}>⌘</Text><Text fw={700}>{t.practice.empty}</Text><Text size="sm" c="dimmed">Thử thay đổi bộ lọc hoặc tham gia thêm lớp học.</Text></Stack></Center></Paper>}
      {q.data && q.data.items.length > 0 && (
        <Paper className="table-card">
        <Table.ScrollContainer minWidth={680}><Table highlightOnHover verticalSpacing="md" horizontalSpacing="lg" data-testid="problem-table">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t.practice.columns.title}</Table.Th>
              <Table.Th>{t.practice.columns.difficulty}</Table.Th>
              <Table.Th>{t.practice.columns.languages}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {q.data.items.map((p) => (
              <Table.Tr key={p.id}>
                <Table.Td><Text fw={650}>{p.title}</Text><Text size="xs" c="dimmed">Sẵn sàng luyện tập</Text></Table.Td>
                <Table.Td>{p.difficulty ? <Badge variant="light" color={p.difficulty === "HARD" ? "red" : p.difficulty === "MEDIUM" ? "yellow" : "teal"}>{difficultyLabel[p.difficulty] ?? p.difficulty}</Badge> : "—"}</Table.Td>
                <Table.Td><Group gap={5}>{p.supported_languages.map((l) => <Badge key={l} color="gray" variant="light">{languageLabel[l] ?? l}</Badge>)}</Group></Table.Td>
                <Table.Td>
                  <Button component={Link} to={`/practice/problems/${p.id}`} size="sm" variant="light">
                    {t.practice.open}
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table></Table.ScrollContainer></Paper>
      )}
      {q.data && q.data.total > PAGE_SIZE && <Group justify="center"><Pagination total={Math.ceil(q.data.total / PAGE_SIZE)} value={page} onChange={setPage} /></Group>}
    </Stack>
  );
}
