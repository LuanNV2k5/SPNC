import { Alert, Button, Group, Loader, Paper, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../../api/client";
import { tt, ts } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";

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
    <Stack>
      <Title order={3}>{ts.title}</Title>
      <Paper withBorder p="sm">
        <form onSubmit={submit}>
          <Group align="flex-end">
            <TextInput label={ts.code} value={code} onChange={(e) => setCode(e.currentTarget.value)} required maxLength={16} name="invite_code" />
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
      {classes.isPending && <Loader />}
      <ErrorAlert error={classes.error} />
      {classes.data && classes.data.items.length === 0 && <Text c="dimmed">{ts.empty}</Text>}
      {classes.data && classes.data.items.length > 0 && (
        <Table data-testid="my-class-table">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{tt.classes.name}</Table.Th>
              <Table.Th>{tt.classes.year}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {classes.data.items.map((c) => (
              <Table.Tr key={c.id}>
                <Table.Td>{c.name}</Table.Td>
                <Table.Td>{c.academic_year}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
