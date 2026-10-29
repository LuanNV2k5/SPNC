import { Badge, Button, Group, Loader, Pagination, Select, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, call } from "../../api/client";
import { difficultyLabel, languageLabel, t } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";

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
    <Stack>
      <Title order={3}>{t.practice.title}</Title>
      <Group>
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
      </Group>
      {q.isPending && <Loader />}
      <ErrorAlert error={q.error} />
      {q.data && q.data.items.length === 0 && <Text c="dimmed">{t.practice.empty}</Text>}
      {q.data && q.data.items.length > 0 && (
        <Table striped highlightOnHover data-testid="problem-table">
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
                <Table.Td>{p.title}</Table.Td>
                <Table.Td>{p.difficulty ? <Badge variant="light">{difficultyLabel[p.difficulty] ?? p.difficulty}</Badge> : "—"}</Table.Td>
                <Table.Td>{p.supported_languages.map((l) => languageLabel[l] ?? l).join(", ")}</Table.Td>
                <Table.Td>
                  <Button component={Link} to={`/practice/problems/${p.id}`} size="xs">
                    {t.practice.open}
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {q.data && q.data.total > PAGE_SIZE && <Pagination total={Math.ceil(q.data.total / PAGE_SIZE)} value={page} onChange={setPage} />}
    </Stack>
  );
}
