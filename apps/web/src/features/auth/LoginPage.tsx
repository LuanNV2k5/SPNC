import { Button, Container, Paper, PasswordInput, Stack, TextInput, Title } from "@mantine/core";
import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { t } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { useAuth } from "./AuthContext";

export function LoginPage() {
  const { status, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (status === "authenticated") return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Container size={420} py={80}>
      <Title order={2} ta="center" mb="lg">
        {t.appName}
      </Title>
      <Paper withBorder p="lg" radius="md">
        <form onSubmit={submit}>
          <Stack>
            <Title order={4}>{t.login.title}</Title>
            <TextInput label={t.login.username} value={username} onChange={(e) => setUsername(e.currentTarget.value)} required autoComplete="username" name="username" />
            <PasswordInput label={t.login.password} value={password} onChange={(e) => setPassword(e.currentTarget.value)} required autoComplete="current-password" name="password" />
            <ErrorAlert error={error} />
            <Button type="submit" loading={busy}>
              {t.login.submit}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Container>
  );
}
