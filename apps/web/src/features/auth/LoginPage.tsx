import { Box, Button, Container, Group, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
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
    <Box className="auth-screen">
    <Container size={460} w="100%" px="md">
      <Stack align="center" mb="xl" gap="sm">
        <Group gap="sm"><Box className="brand-mark">SP</Box><Title order={2}>SPNC</Title></Group>
        <Text c="dimmed" ta="center">Không gian học và giảng dạy lập trình trực quan</Text>
      </Stack>
      <Paper className="auth-card" withBorder p={{ base: "lg", sm: 32 }} radius="xl">
        <form onSubmit={submit}>
          <Stack gap="lg">
            <Box><Title order={3}>{t.login.title}</Title><Text size="sm" c="dimmed" mt={5}>Chào mừng bạn quay lại. Nhập thông tin để tiếp tục.</Text></Box>
            <TextInput label={t.login.username} value={username} onChange={(e) => setUsername(e.currentTarget.value)} required autoComplete="username" name="username" />
            <PasswordInput label={t.login.password} value={password} onChange={(e) => setPassword(e.currentTarget.value)} required autoComplete="current-password" name="password" />
            <ErrorAlert error={error} />
            <Button type="submit" loading={busy} size="md" fullWidth>
              {t.login.submit}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Container>
    </Box>
  );
}
