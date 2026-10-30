import { Badge, Box, Button, Center, Group, Loader, Paper, Stack, Table, Text, TextInput } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { PageHeader } from "../../ui/PageHeader";
import { createClass, keys, listClasses } from "./teacherApi";

export function ClassesPage() {
  const qc = useQueryClient();
  const classes = useQuery({ queryKey: keys.classes(), queryFn: listClasses });
  const [name, setName] = useState("");
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const create = useMutation({
    mutationFn: () => createClass(name, year),
    onSuccess: () => {
      setName("");
      void qc.invalidateQueries({ queryKey: keys.classes() });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <Stack gap="xl">
      <PageHeader eyebrow="Không gian giảng viên" title={tt.classes.title} description="Tạo lớp, chia sẻ mã tham gia và theo dõi hoạt động học tập." />
      <Paper className="surface-card" p="lg">
        <form onSubmit={submit}>
          <Group align="flex-end">
            <Box style={{ flex: "1 1 300px" }}><Text fw={700}>Tạo lớp học mới</Text><Text size="sm" c="dimmed" mb="sm">Mã tham gia sẽ được tạo tự động sau khi lưu.</Text><TextInput label={tt.classes.name} value={name} onChange={(e) => setName(e.currentTarget.value)} required name="class_name" /></Box>
            <TextInput label={tt.classes.year} value={year} onChange={(e) => setYear(e.currentTarget.value)} required w={140} name="academic_year" />
            <Button type="submit" loading={create.isPending}>
              {tt.classes.create}
            </Button>
          </Group>
        </form>
        <ErrorAlert error={create.error} />
      </Paper>
      {classes.isPending && <Center py="xl"><Loader /></Center>}
      <ErrorAlert error={classes.error} />
      {classes.data && classes.data.items.length === 0 && <Paper className="empty-panel" p={48}><Center><Stack align="center" gap={5}><Text fz={32}>▦</Text><Text fw={700}>{tt.classes.empty}</Text><Text size="sm" c="dimmed">Lớp mới sẽ xuất hiện tại đây cùng mã mời.</Text></Stack></Center></Paper>}
      {classes.data && classes.data.items.length > 0 && (
        <Paper className="table-card"><Table.ScrollContainer minWidth={650}><Table highlightOnHover verticalSpacing="md" horizontalSpacing="lg" data-testid="class-table">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{tt.classes.name}</Table.Th>
              <Table.Th>{tt.classes.year}</Table.Th>
              <Table.Th>{tt.classes.inviteCode}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {classes.data.items.map((c) => (
              <Table.Tr key={c.id}>
                <Table.Td><Group gap="sm"><Badge size="lg" circle color="indigo">{c.name.charAt(0).toUpperCase()}</Badge><Text fw={650}>{c.name}</Text></Group></Table.Td>
                <Table.Td><Badge variant="light" color="gray">{c.academic_year}</Badge></Table.Td>
                <Table.Td>
                  <Badge variant="outline" color="indigo" ff="monospace">{c.invite_code}</Badge>
                </Table.Td>
                <Table.Td>
                  <Button component={Link} to={`/teacher/classes/${c.id}`} size="sm" variant="light">
                    {tt.classes.open}
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table></Table.ScrollContainer></Paper>
      )}
    </Stack>
  );
}
