import { Alert, Badge, Box, Button, Center, Group, Loader, Paper, Select, Stack, Table, Text, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { keys, listClasses } from "./teacherApi";
import { listPublications, problemKeys, publishProblem, type Problem, unpublishProblem } from "./problemApi";

export function PublicationsPanel({ problem }: { problem: Problem }) {
  const qc = useQueryClient();
  const [classId, setClassId] = useState<string | null>(null);
  const classes = useQuery({ queryKey: keys.classes(), queryFn: listClasses });
  const publications = useQuery({ queryKey: problemKeys.publications(problem.id), queryFn: () => listPublications(problem.id) });
  const refresh = () => void qc.invalidateQueries({ queryKey: problemKeys.publications(problem.id) });
  const publish = useMutation({ mutationFn: () => publishProblem(problem.id, classId!), onSuccess: () => { setClassId(null); refresh(); } });
  const unpublish = useMutation({ mutationFn: (id: string) => unpublishProblem(problem.id, id), onSuccess: refresh });
  const published = new Set(publications.data?.items.map((item) => item.class_id));
  const classById = new Map(classes.data?.items.map((item) => [item.id, item]));
  const available = classes.data?.items.filter((item) => !published.has(item.id)).map((item) => ({ value: item.id, label: `${item.name} (${item.academic_year})` })) ?? [];

  return (
    <Stack gap="xl">
      <Box>
        <Title order={4}>Phát hành tới lớp</Title>
        <Text size="sm" c="dimmed" mt={5}>Chọn lớp sẽ nhìn thấy bài tập. Bạn có thể thu hồi mà không xóa nội dung đề.</Text>
      </Box>
      {problem.visibility === "PRIVATE" && <Alert color="yellow">{tt.problems.publications.privateHint}</Alert>}
      <Paper withBorder p="lg" bg="gray.0">
      <Group align="flex-end" wrap="wrap">
        <Select
          label={tt.problems.publications.chooseClass}
          placeholder={available.length ? tt.problems.publications.chooseClass : tt.problems.publications.noAvailable}
          data={available}
          value={classId}
          onChange={setClassId}
          disabled={problem.visibility === "PRIVATE" || available.length === 0}
          searchable
          style={{ flex: "1 1 280px" }}
        />
        <Button onClick={() => publish.mutate()} disabled={!classId || problem.visibility === "PRIVATE"} loading={publish.isPending}>{tt.problems.publications.publish}</Button>
      </Group>
      </Paper>
      <ErrorAlert error={publish.error ?? unpublish.error ?? classes.error ?? publications.error} />
      {(classes.isPending || publications.isPending) && <Center py="xl"><Loader /></Center>}
      {publications.data?.items.length === 0 && <Center py="xl"><Stack align="center" gap={4}><Text fz={30}>◎</Text><Text fw={650}>{tt.problems.publications.empty}</Text><Text size="sm" c="dimmed">Chọn một lớp ở phía trên để bắt đầu.</Text></Stack></Center>}
      {!!publications.data?.items.length && (
        <Table highlightOnHover verticalSpacing="md" data-testid="publication-table">
          <Table.Thead><Table.Tr><Table.Th>{tt.problems.publications.className}</Table.Th><Table.Th>{tt.problems.publications.publishedAt}</Table.Th><Table.Th>Trạng thái</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {publications.data.items.map((item) => (
              <Table.Tr key={item.id}>
                <Table.Td>{classById.get(item.class_id)?.name ?? item.class_id}</Table.Td>
                <Table.Td>{new Date(item.created_at).toLocaleString("vi-VN")}</Table.Td>
                <Table.Td><Badge color="teal" variant="light">Đang phát hành</Badge></Table.Td>
                <Table.Td><Button size="compact-xs" variant="subtle" color="red" loading={unpublish.isPending} onClick={() => window.confirm(tt.problems.publications.unpublishConfirm) && unpublish.mutate(item.class_id)}>{tt.problems.publications.unpublish}</Button></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
