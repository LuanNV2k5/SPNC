import { Badge, Box, Button, Center, Grid, Group, Loader, Paper, Select, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { t, tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { Annotations } from "./Annotations";
import { LiveBadge } from "./LiveBadge";
import { useLive } from "./LiveProvider";
import { SignalCard } from "./SignalCard";
import { keys, listMembers, listSessions, listSignals } from "./teacherApi";

const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("vi-VN") : "—");

export function StudentPage() {
  const { classId = "", studentId = "" } = useParams();
  const live = useLive();
  useEffect(() => live.watch(classId), [live, classId]);
  const [status, setStatus] = useState<string | null>("NEW");
  const [type, setType] = useState<string | null>(null);

  const members = useQuery({ queryKey: keys.members(classId), queryFn: () => listMembers(classId) });
  const sessions = useQuery({ queryKey: keys.sessions(classId, studentId), queryFn: () => listSessions(classId, studentId) });
  const signals = useQuery({
    queryKey: [...keys.signals(classId, studentId), status, type],
    queryFn: () => listSignals(classId, studentId, { status: status ?? undefined, signal_type: type ?? undefined }),
  });
  const member = members.data?.items.find((m) => m.student_id === studentId);

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end"><Box><Text size="xs" fw={700} c="indigo" tt="uppercase" lts="0.1em">Hồ sơ học tập</Text><Title order={2} mt={4}>{member?.full_name ?? studentId}</Title><Text c="dimmed" mt={5}>{member?.username} · Các phiên làm bài và tín hiệu hỗ trợ</Text></Box><LiveBadge /></Group>
      <Grid>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Paper className="surface-card" p="lg"><Title order={4} mb="lg">
            {tt.student.sessions}
          </Title>
          {sessions.isPending && <Center py="xl"><Loader /></Center>}
          <ErrorAlert error={sessions.error} />
          {sessions.data && sessions.data.items.length === 0 && <Text c="dimmed">{tt.student.noSessions}</Text>}
          {sessions.data && sessions.data.items.length > 0 && (
            <Table.ScrollContainer minWidth={760}><Table highlightOnHover data-testid="session-table" verticalSpacing="md">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{tt.student.problem}</Table.Th>
                  <Table.Th>{tt.student.opened}</Table.Th>
                  <Table.Th>{tt.student.status}</Table.Th>
                  <Table.Th>{tt.student.verdict}</Table.Th>
                  <Table.Th>{tt.student.signalCount}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sessions.data.items.map((s) => (
                  <Table.Tr key={s.id}>
                    <Table.Td>
                      {s.problem_title}
                      <Text size="xs" c="dimmed">
                        {tt.context[s.context] ?? s.context}
                        {s.exam_title ? ` · ${s.exam_title}` : ""}
                      </Text>
                    </Table.Td>
                    <Table.Td>{fmt(s.opened_at)}</Table.Td>
                    <Table.Td>
                      <Badge variant="light" color={s.status === "ACTIVE" ? "green" : "gray"}>
                        {tt.sessionStatus[s.status] ?? s.status}
                      </Badge>
                    </Table.Td>
                    <Table.Td>{s.latest_submission_verdict ? (t.verdicts[s.latest_submission_verdict] ?? s.latest_submission_verdict) : "—"}</Table.Td>
                    <Table.Td>{s.signal_count}</Table.Td>
                    <Table.Td>
                      <Button component={Link} to={`/teacher/classes/${classId}/students/${studentId}/sessions/${s.id}`} size="xs">
                        {tt.klass.view}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table></Table.ScrollContainer>
          )}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Paper className="surface-card" p="lg"><Stack>
            <Box><Title order={4}>{tt.student.signals}</Title><Text size="sm" c="dimmed">Tín hiệu giúp ưu tiên quan sát, không thay thế đánh giá của giảng viên.</Text></Box>
            <Group>
              <Select
                size="xs"
                label={tt.student.filterStatus}
                clearable
                value={status}
                onChange={setStatus}
                data={Object.entries(tt.signalStatus).map(([value, label]) => ({ value, label }))}
              />
              <Select size="xs" label={tt.student.filterType} clearable value={type} onChange={setType} data={Object.entries(tt.signalType).map(([value, label]) => ({ value, label }))} />
            </Group>
            <ErrorAlert error={signals.error} />
            {signals.data && signals.data.items.length === 0 && <Text c="dimmed">{tt.student.noSignals}</Text>}
            {signals.data?.items.map((s) => <SignalCard key={s.id} classId={classId} signal={s} />)}
            <Annotations studentId={studentId} />
          </Stack></Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
