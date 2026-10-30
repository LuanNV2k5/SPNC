import { Badge, Box, Button, Center, Code, CopyButton, Group, Loader, Paper, Stack, Table, Tabs, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useParams } from "react-router";
import { tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { PageHeader } from "../../ui/PageHeader";
import { LiveBadge } from "./LiveBadge";
import { useLive } from "./LiveProvider";
import { getClass, keys, listAttention, listMembers, rotateInvite } from "./teacherApi";

const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("vi-VN") : "—");

export function ClassPage() {
  const { classId = "" } = useParams();
  const qc = useQueryClient();
  const live = useLive();
  useEffect(() => live.watch(classId), [live, classId]);

  const klass = useQuery({ queryKey: keys.klass(classId), queryFn: () => getClass(classId) });
  const attention = useQuery({ queryKey: keys.attention(classId), queryFn: () => listAttention(classId) });
  const members = useQuery({ queryKey: keys.members(classId), queryFn: () => listMembers(classId) });
  const rotate = useMutation({
    mutationFn: () => rotateInvite(classId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.klass(classId) });
      void qc.invalidateQueries({ queryKey: keys.classes() });
    },
  });
  const studentLink = (studentId: string) => `/teacher/classes/${classId}/students/${studentId}`;

  if (klass.isPending) return <Center py={80}><Loader /></Center>;
  if (!klass.data) return <ErrorAlert error={klass.error} />;

  return (
    <Stack gap="xl">
      <PageHeader eyebrow="Chi tiết lớp học" title={klass.data.name} description={`Năm học ${klass.data.academic_year} · Theo dõi học sinh cần hỗ trợ theo thời gian thực.`} action={<LiveBadge />} />
      <Paper className="surface-card" p="lg">
      <Group gap="sm" justify="space-between">
        <Box><Text size="xs" c="dimmed" fw={650} tt="uppercase">{tt.classes.inviteCode}</Text><Code fz="lg" fw={700} mt={5} data-testid="invite-code">{klass.data.invite_code}</Code></Box>
        <Group gap="xs">
        <CopyButton value={klass.data.invite_code}>
          {({ copied, copy }) => (
            <Button size="compact-xs" variant="subtle" onClick={copy}>
              {copied ? "✓" : tt.classes.copy}
            </Button>
          )}
        </CopyButton>
        <Button size="compact-xs" variant="subtle" color="orange" loading={rotate.isPending} onClick={() => window.confirm(tt.classes.rotateConfirm) && rotate.mutate()}>
          {tt.classes.rotate}
        </Button>
        </Group>
      </Group>
      </Paper>
      <ErrorAlert error={rotate.error} />
      <Tabs defaultValue="attention" className="editor-tabs">
        <Tabs.List>
          <Tabs.Tab value="attention">
            {tt.klass.attention} {attention.data && attention.data.total > 0 && <Badge size="sm" ml={4}>{attention.data.total}</Badge>}
          </Tabs.Tab>
          <Tabs.Tab value="roster">{tt.klass.roster}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="attention" pt="xl">
          <Paper className="table-card" p={attention.data?.items.length === 0 ? "xl" : 0}>
          <ErrorAlert error={attention.error} />
          {attention.data && attention.data.items.length === 0 && <Center py="xl"><Stack align="center" gap={5}><Text fz={30}>✓</Text><Text fw={700}>{tt.klass.noAttention}</Text><Text size="sm" c="dimmed">Không có tín hiệu mới cần xử lý.</Text></Stack></Center>}
          {attention.data && attention.data.items.length > 0 && (
            <Table.ScrollContainer minWidth={720}><Table data-testid="attention-table" verticalSpacing="md" horizontalSpacing="lg" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{tt.klass.fullName}</Table.Th>
                  <Table.Th>{tt.klass.newSignals}</Table.Th>
                  <Table.Th>{tt.klass.latest}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {attention.data.items.map((a) => (
                  <Table.Tr key={a.student_id}>
                    <Table.Td>
                      {a.full_name} <Text span c="dimmed" size="xs">{a.username}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        {Object.entries(a.counts_by_type).map(([type, n]) => (
                          <Badge key={type} variant="light">
                            {tt.signalType[type] ?? type}: {n}
                          </Badge>
                        ))}
                      </Group>
                    </Table.Td>
                    <Table.Td>{fmt(a.latest_detected_at)}</Table.Td>
                    <Table.Td>
                      <Button component={Link} to={studentLink(a.student_id)} size="xs">
                        {tt.klass.view}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table></Table.ScrollContainer>
          )}
          </Paper>
        </Tabs.Panel>
        <Tabs.Panel value="roster" pt="xl">
          <Paper className="table-card" p={members.data?.items.length === 0 ? "xl" : 0}>
          <ErrorAlert error={members.error} />
          {members.data && members.data.items.length === 0 && <Text c="dimmed">{tt.klass.noMembers}</Text>}
          {members.data && members.data.items.length > 0 && (
            <Table.ScrollContainer minWidth={650}><Table data-testid="roster-table" verticalSpacing="md" horizontalSpacing="lg" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{tt.klass.fullName}</Table.Th>
                  <Table.Th>{tt.klass.username}</Table.Th>
                  <Table.Th>{tt.klass.joinedAt}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {members.data.items.map((m) => (
                  <Table.Tr key={m.student_id}>
                    <Table.Td>{m.full_name ?? "—"}</Table.Td>
                    <Table.Td>{m.username ?? m.student_id}</Table.Td>
                    <Table.Td>{fmt(m.created_at)}</Table.Td>
                    <Table.Td>
                      <Button component={Link} to={studentLink(m.student_id)} size="xs" variant="light">
                        {tt.klass.view}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table></Table.ScrollContainer>
          )}
          </Paper>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
