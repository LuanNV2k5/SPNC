import { Button, Group, Paper, Select, Stack, Text, Textarea, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { tt } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { createAnnotation, deleteAnnotation, keys, listAnnotations, updateAnnotation, type Annotation, type Signal } from "./teacherApi";

function Item({ a, onChanged }: { a: Annotation; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(a.content);
  const save = useMutation({ mutationFn: () => updateAnnotation(a.id, text), onSuccess: () => (setEditing(false), onChanged()) });
  const del = useMutation({ mutationFn: () => deleteAnnotation(a.id), onSuccess: onChanged });
  return (
    <Paper withBorder p="xs" data-testid="annotation">
      {editing ? (
        <Stack gap={4}>
          <Textarea value={text} onChange={(e) => setText(e.currentTarget.value)} autosize minRows={2} maxLength={5000} />
          <Group gap={4}>
            <Button size="compact-xs" onClick={() => save.mutate()} loading={save.isPending}>
              {tt.annotations.save}
            </Button>
            <Button size="compact-xs" variant="default" onClick={() => setEditing(false)}>
              ✕
            </Button>
          </Group>
        </Stack>
      ) : (
        <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
          {a.content}
        </Text>
      )}
      <Group justify="space-between" mt={4}>
        <Text size="xs" c="dimmed">
          {new Date(a.updated_at).toLocaleString("vi-VN")}
          {a.signal_id ? ` · ${tt.annotations.forSignal}` : ""}
        </Text>
        {!editing && (
          <Group gap={4}>
            <Button size="compact-xs" variant="subtle" onClick={() => setEditing(true)}>
              {tt.annotations.edit}
            </Button>
            <Button size="compact-xs" variant="subtle" color="red" onClick={() => window.confirm(tt.annotations.deleteConfirm) && del.mutate()}>
              {tt.annotations.delete}
            </Button>
          </Group>
        )}
      </Group>
      <ErrorAlert error={save.error ?? del.error} />
    </Paper>
  );
}

/** The teacher's own notes for a student, optionally for one session (docs/47 D8). */
export function Annotations({ studentId, sessionId, signals = [] }: { studentId: string; sessionId?: string; signals?: Signal[] }) {
  const qc = useQueryClient();
  const key = [...keys.annotations(studentId), sessionId ?? "all"];
  const list = useQuery({ queryKey: key, queryFn: () => listAnnotations(studentId, sessionId) });
  const [text, setText] = useState("");
  const [signalId, setSignalId] = useState<string | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: keys.annotations(studentId) });
  const add = useMutation({
    mutationFn: () => createAnnotation({ student_id: studentId, session_id: sessionId, signal_id: signalId ?? undefined, content: text }),
    onSuccess: () => {
      setText("");
      setSignalId(null);
      refresh();
    },
  });

  return (
    <Stack gap="xs">
      <Title order={5}>{tt.annotations.title}</Title>
      {sessionId && (
        <Stack gap={4}>
          <Textarea placeholder={tt.annotations.placeholder} value={text} onChange={(e) => setText(e.currentTarget.value)} autosize minRows={2} maxLength={5000} name="annotation" />
          <Group gap="xs">
            {signals.length > 0 && (
              <Select
                size="xs"
                clearable
                placeholder={tt.annotations.forSignal}
                value={signalId}
                onChange={setSignalId}
                data={signals.map((s) => ({ value: s.id, label: `${tt.signalType[s.signal_type] ?? s.signal_type} · ${new Date(s.detected_at).toLocaleTimeString("vi-VN")}` }))}
              />
            )}
            <Button size="xs" onClick={() => add.mutate()} disabled={!text.trim()} loading={add.isPending}>
              {tt.annotations.add}
            </Button>
          </Group>
          <ErrorAlert error={add.error} />
        </Stack>
      )}
      <ErrorAlert error={list.error} />
      {list.data && list.data.items.length === 0 && <Text c="dimmed" size="sm">{tt.annotations.empty}</Text>}
      {list.data?.items.map((a) => <Item key={a.id} a={a} onChanged={refresh} />)}
    </Stack>
  );
}
