import { AppShell, Button, Center, Group, Loader, Text, Title } from "@mantine/core";
import { Link, Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "../features/auth/AuthContext";
import { t } from "../i18n/vi";

/** Route guard: UX only, authorization stays on the backend (docs/46 §3.4). */
export function RequireAuth() {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === "loading") {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }
  if (status === "anonymous" || !user) return <Navigate to="/login" replace />;
  if (user.force_password_change && location.pathname !== "/change-password") return <Navigate to="/change-password" replace />;
  return <Outlet />;
}

export function AppLayout() {
  const { user, logout, pendingTrace } = useAuth();
  const doLogout = async () => {
    const n = await pendingTrace();
    if (n > 0 && !window.confirm(t.logoutPending(n))) return;
    await logout();
  };
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Title order={4}>SPNC</Title>
            {user?.role === "STUDENT" && (
              <Button component={Link} to="/practice" variant="subtle">
                {t.nav.practice}
              </Button>
            )}
          </Group>
          <Group>
            <Text size="sm" data-testid="current-user">
              {user?.full_name} ({user?.role})
            </Text>
            <Button variant="default" size="xs" onClick={() => void doLogout()}>
              {t.nav.logout}
            </Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

export function RoleHome() {
  const { user } = useAuth();
  return user?.role === "STUDENT" ? <Navigate to="/practice" replace /> : <Placeholder />;
}

export function Placeholder() {
  return (
    <Center py={80} style={{ flexDirection: "column" }}>
      <Title order={3}>{t.placeholder.title}</Title>
      <Text c="dimmed" mt="sm">
        {t.placeholder.body}
      </Text>
    </Center>
  );
}
