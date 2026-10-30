import { Box, Button, Container, Paper, PasswordInput, Stack, Text, Title } from "@mantine/core";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";
import { api, call } from "../../api/client";
import { ApiError } from "../../api/errors";
import { t } from "../../i18n/vi";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { useAuth } from "./AuthContext";

export function ChangePasswordPage() {
  const { status, user, login } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (status === "anonymous" || !user) return <Navigate to="/login" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== confirm) {
      setError(new ApiError(null, "VALIDATION_ERROR", t.changePassword.mismatch, ""));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await call(api.POST("/api/v1/auth/change-password", { body: { current_password: current, new_password: next } }));
      // The server revoked every refresh session (docs/46 F4): log in again with the new password
      await login(user.username, next);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box className="auth-screen">
    <Container size={460} w="100%" px="md">
      <Paper className="auth-card" withBorder p={{ base: "lg", sm: 32 }} radius="xl">
        <form onSubmit={submit}>
          <Stack gap="lg">
            <Box><Text size="xs" fw={700} c="indigo" tt="uppercase">Bảo mật tài khoản</Text><Title order={3} mt={4}>{t.changePassword.title}</Title></Box>
            {user.force_password_change && <Text size="sm">{t.changePassword.intro}</Text>}
            <PasswordInput label={t.changePassword.current} value={current} onChange={(e) => setCurrent(e.currentTarget.value)} required autoComplete="current-password" name="current_password" />
            <PasswordInput label={t.changePassword.next} value={next} onChange={(e) => setNext(e.currentTarget.value)} required autoComplete="new-password" name="new_password" />
            <PasswordInput label={t.changePassword.confirm} value={confirm} onChange={(e) => setConfirm(e.currentTarget.value)} required autoComplete="new-password" name="confirm_password" />
            <ErrorAlert error={error} />
            <Button type="submit" loading={busy} size="md">
              {t.changePassword.submit}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Container>
    </Box>
  );
}
