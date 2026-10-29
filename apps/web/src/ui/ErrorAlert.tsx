import { Alert, Button, Code, Group, List, Text } from "@mantine/core";
import { useState } from "react";
import { toApiError } from "../api/errors";
import { errorText, t } from "../i18n/vi";

interface FieldError {
  loc?: unknown[];
  msg?: string;
}

/** Shows error_code, a readable text and a copyable request_id for any error (docs/46 §3.4). */
export function ErrorAlert({ error, title }: { error: unknown; title?: string }) {
  const [copied, setCopied] = useState(false);
  if (!error) return null;
  const e = toApiError(error);
  const fields = Array.isArray(e.details) ? (e.details as FieldError[]) : [];
  const copy = () => {
    void navigator.clipboard?.writeText(e.requestId).then(() => setCopied(true));
  };
  return (
    <Alert color="red" title={title ?? t.error.title} data-testid="error-alert" data-error-code={e.errorCode}>
      <Text size="sm">{errorText(e.errorCode, e.message)}</Text>
      {fields.length > 0 && (
        <List size="sm" mt="xs">
          {fields.map((f, i) => (
            <List.Item key={i}>
              {(f.loc ?? []).slice(1).join(".")}: {f.msg}
            </List.Item>
          ))}
        </List>
      )}
      <Group gap="xs" mt="xs">
        <Code>{e.errorCode}</Code>
        {e.requestId && (
          <>
            <Text size="xs" c="dimmed">
              {t.error.requestId}: <Code data-testid="request-id">{e.requestId}</Code>
            </Text>
            <Button size="compact-xs" variant="subtle" onClick={copy}>
              {copied ? t.error.copied : t.error.copy}
            </Button>
          </>
        )}
      </Group>
    </Alert>
  );
}
