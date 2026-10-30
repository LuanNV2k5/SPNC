import { Button, Group, Loader, Paper, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
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
    <Stack>
      <Title order={3}>{tt.classes.title}</Title>
      <Paper withBorder p="sm">
        <form onSubmit={submit}>
          <Group align="flex-end">
            <TextInput label={tt.classes.name} value={name} onChange={(e) => setName(e.currentTarget.value)} required name="class_name" />
            <TextInput label={tt.classes.year} value={year} onChange={(e) => setYear(e.currentTarget.value)} required w={120} name="academic_year" />
            <Button type="submit" loading={create.isPending}>
              {tt.classes.create}
            </Button>
          </Group>
        </form>
        <ErrorAlert error={create.error} />
      </Paper>
      {classes.isPending && <Loader />}
      <ErrorAlert error={classes.error} />
      {classes.data && classes.data.items.length === 0 && <Text c="dimmed">{tt.classes.empty}</Text>}
      {classes.data && classes.data.items.length > 0 && (
        <Table striped highlightOnHover data-testid="class-table">
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
                <Table.Td>{c.name}</Table.Td>
                <Table.Td>{c.academic_year}</Table.Td>
                <Table.Td>
                  <code>{c.invite_code}</code>
                </Table.Td>
                <Table.Td>
                  <Button component={Link} to={`/teacher/classes/${c.id}`} size="xs">
                    {tt.classes.open}
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
