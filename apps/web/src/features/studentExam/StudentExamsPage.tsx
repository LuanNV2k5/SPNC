import { Badge, Button, Center, Loader, Paper, Stack, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { PageHeader } from "../../ui/PageHeader";
import { listExams } from "./studentExamApi";

const statusLabel: Record<string, string> = {
  DRAFT: "Bản nháp", SCHEDULED: "Sắp diễn ra", ONGOING: "Đang diễn ra", ENDED: "Đã kết thúc", CANCELLED: "Đã hủy",
};

export function StudentExamsPage() {
  const exams = useQuery({ queryKey: ["student-exams"], queryFn: listExams });
  return (
    <Stack gap="lg">
      <PageHeader eyebrow="Không gian sinh viên" title="Kỳ thi" description="Xem lịch và trạng thái các kỳ thi được giao cho bạn." />
      <ErrorAlert error={exams.error} />
      {exams.isPending && <Center py="xl"><Loader /></Center>}
      {exams.data && exams.data.items.length === 0 && <Paper p="xl"><Text c="dimmed">Hiện chưa có kỳ thi được giao.</Text></Paper>}
      {exams.data && exams.data.items.length > 0 && (
        <Paper className="table-card">
          <Table.ScrollContainer minWidth={620}><Table highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>Kỳ thi</Table.Th><Table.Th>Thời gian</Table.Th><Table.Th>Trạng thái</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>{exams.data.items.map((exam) => <Table.Tr key={exam.id}>
              <Table.Td><Text fw={600}>{exam.title}</Text>{exam.description && <Text size="sm" c="dimmed" lineClamp={2}>{exam.description}</Text>}</Table.Td>
              <Table.Td><Text size="sm">{new Date(exam.start_time).toLocaleString("vi-VN")}</Text><Text size="sm" c="dimmed">đến {new Date(exam.end_time).toLocaleString("vi-VN")}</Text></Table.Td>
              <Table.Td><Badge>{statusLabel[exam.status] ?? exam.status}</Badge></Table.Td>
              <Table.Td><Button component={Link} to={`/student/exams/${exam.id}`} size="sm" variant="light">Chi tiết</Button></Table.Td>
            </Table.Tr>)}</Table.Tbody>
          </Table></Table.ScrollContainer>
        </Paper>
      )}
    </Stack>
  );
}
