import { Badge, Button, Code, Collapse, Group, Paper, Table, Text } from "@mantine/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { evidenceFields, signalSummary, tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { keys, setSignalStatus, type Signal, type SignalStatus } from "./teacherApi";

const show = (v: unknown) => {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "string" && /^\d{4}-\d\d-\d\dT/.test(v)) return new Date(v).toLocaleString("vi-VN");
  if (typeof v === "number") return String(Math.round(v * 100) / 100);
  return String(v);
};

/** One attention signal: neutral summary, canonical evidence, status actions (docs/47 D6). */
export function SignalCard({ classId, signal, onGoTo }: { classId: string; signal: Signal; onGoTo?: (s: Signal) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const change = useMutation({
    mutationFn: (status: SignalStatus) => setSignalStatus(classId, signal.student_id, signal.id, status),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
  });
  const ev = signal.evidence as Record<string, unknown>;
  return (
    <Paper withBorder p="md" data-testid="signal-card" data-signal-type={signal.signal_type} data-status={signal.status} bg={signal.status === "NEW" ? "orange.0" : "white"}>
      <Group justify="space-between" align="flex-start">
        <div>
          <Group gap="xs">
            <Badge variant="light">{tt.signalType[signal.signal_type] ?? signal.signal_type}</Badge>
            <Badge color={signal.status === "NEW" ? "blue" : "gray"} variant="outline">
              {tt.signalStatus[signal.status] ?? signal.status}
            </Badge>
            <Text size="xs" c="dimmed">
              {new Date(signal.detected_at).toLocaleString("vi-VN")}
            </Text>
          </Group>
          <Text size="sm" mt={4}>
            {signalSummary(signal.signal_type, ev)}
          </Text>
        </div>
        <Group gap={4}>
          {onGoTo && (
            <Button size="compact-xs" variant="subtle" onClick={() => onGoTo(signal)}>
              {tt.session.goTo}
            </Button>
          )}
          {signal.status === "NEW" ? (
            <>
              <Button size="compact-xs" onClick={() => change.mutate("ACKNOWLEDGED")} loading={change.isPending}>
                {tt.signalActions.ack}
              </Button>
              <Button size="compact-xs" variant="default" onClick={() => change.mutate("DISMISSED")} loading={change.isPending}>
                {tt.signalActions.dismiss}
              </Button>
            </>
          ) : (
            <Button size="compact-xs" variant="default" onClick={() => change.mutate("NEW")} loading={change.isPending}>
              {tt.signalActions.reopen}
            </Button>
          )}
        </Group>
      </Group>
      <Table mt="xs" withRowBorders={false} verticalSpacing={2}>
        <Table.Tbody>
          {(evidenceFields[signal.signal_type] ?? []).map(([field, caption]) => (
            <Table.Tr key={field}>
              <Table.Td c="dimmed" w={180}>
                {caption}
              </Table.Td>
              <Table.Td>{show(ev[field])}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Button size="compact-xs" variant="subtle" onClick={() => setOpen((o) => !o)}>
        {tt.session.details}
      </Button>
      <Collapse in={open}>
        <Code block>{JSON.stringify(signal.evidence, null, 2)}</Code>
        <Text size="xs" c="dimmed">
          rule {signal.rule_version ?? "—"}
        </Text>
      </Collapse>
      <ErrorAlert error={change.error} />
    </Paper>
  );
}
