import { Alert, Badge, Box, Button, Center, Group, Loader, Paper, Stack, Table, Text, TextInput } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../../api/client";
import { tt, ts } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { PageHeader } from "../../ui/PageHeader";

/** Student: joined classes and join-by-invite-code (docs/47 §3.5). */
export function MyClassesPage() {
  const qc = useQueryClient();
  const classes = useQuery({ queryKey: ["my-classes"], queryFn: () => call(api.GET("/api/v1/my/classes", { params: { query: { page: 1, size: 100 } } })) });
  const [code, setCode] = useState("");
  const join = useMutation({
    mutationFn: () => call(api.POST("/api/v1/my/classes/join", { body: { invite_code: code.trim() } })),
    onSuccess: () => {
      setCode("");
      void qc.invalidateQueries({ queryKey: ["my-classes"] });
      void qc.invalidateQueries({ queryKey: ["practice-problems"] });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    join.mutate();
  };

  return (
    <Stack gap="xl">
      <PageHeader eyebrow="Không gian sinh viên" title={ts.title} description="Tham gia lớp bằng mã mời do giảng viên cung cấp." />
      <Paper className="surface-card" p="lg">
        <form onSubmit={submit}>
          <Group align="flex-end" justify="space-between">
            <Box style={{ flex: "1 1 260px" }}><Text fw={700}>Tham gia lớp mới</Text><Text size="sm" c="dimmed" mb="sm">Mã không phân biệt chữ hoa và chữ thường.</Text><TextInput label={ts.code} placeholder="Ví dụ: ABCD1234" value={code} onChange={(e) => setCode(e.currentTarget.value)} required maxLength={16} name="invite_code" /></Box>
            <Button type="submit" loading={join.isPending}>
              {ts.join}
            </Button>
          </Group>
        </form>
        {join.isSuccess && (
          <Alert color="green" mt="xs" data-testid="join-ok">
            {ts.joined}
          </Alert>
        )}
        <ErrorAlert error={join.error} />
      </Paper>
      {classes.isPending && <Center py="xl"><Loader /></Center>}
      <ErrorAlert error={classes.error} />
      {classes.data && classes.data.items.length === 0 && <Paper className="empty-panel" p={48}><Center><Stack align="center" gap={5}><Text fz={32}>▦</Text><Text fw={700}>{ts.empty}</Text><Text size="sm" c="dimmed">Nhập mã mời phía trên để lớp xuất hiện tại đây.</Text></Stack></Center></Paper>}
      {classes.data && classes.data.items.length > 0 && (
        <Paper className="table-card"><Table data-testid="my-class-table" verticalSpacing="md" horizontalSpacing="lg">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{tt.classes.name}</Table.Th>
              <Table.Th>{tt.classes.year}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {classes.data.items.map((c) => (
              <Table.Tr key={c.id}>
                <Table.Td><Group gap="sm"><Badge size="lg" circle color="indigo">{c.name.charAt(0).toUpperCase()}</Badge><Text fw={650}>{c.name}</Text></Group></Table.Td>
                <Table.Td><Badge variant="light" color="gray">{c.academic_year}</Badge></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table></Paper>
      )}
    </Stack>
  );
}
