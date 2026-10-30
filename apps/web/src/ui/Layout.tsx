import { AppShell, Avatar, Badge, Box, Burger, Button, Center, Divider, Group, Loader, NavLink, Stack, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { Link, Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "../features/auth/AuthContext";
import { t, ts, tt } from "../i18n/vi";

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
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();
  const doLogout = async () => {
    const n = await pendingTrace();
    if (n > 0 && !window.confirm(t.logoutPending(n))) return;
    await logout();
  };
  const studentLinks = [
    { to: "/practice", label: t.nav.practice, caption: "Bài tập và tiến độ" },
    { to: "/classes", label: ts.title, caption: "Các lớp đang tham gia" },
  ];
  const teacherLinks = [
    { to: "/teacher/classes", label: tt.nav.classes, caption: "Lớp học và học sinh" },
    { to: "/teacher/problems", label: tt.nav.problems, caption: "Kho đề và phát hành" },
    { to: "/teacher/exams", label: "Kỳ thi", caption: "Lịch thi và tình trạng làm bài" },
  ];
  const links = user?.role === "TEACHER" ? teacherLinks : studentLinks;
  const initials = user?.full_name.split(/\s+/).filter(Boolean).slice(-2).map((part) => part[0]).join("").toUpperCase() || "U";
  return (
    <AppShell header={{ height: 68 }} navbar={{ width: 260, breakpoint: "md", collapsed: { mobile: !opened } }} padding={{ base: "md", sm: "xl" }}>
      <AppShell.Header className="app-header">
        <Group h="100%" px={{ base: "md", sm: "xl" }} justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="md" size="sm" aria-label="Mở điều hướng" />
            <Box className="brand-mark">SP</Box>
            <Box>
              <Title order={4} lh={1.1}>SPNC</Title>
              <Text size="xs" c="dimmed" className="desktop-only">Nền tảng học lập trình</Text>
            </Box>
          </Group>
          <Group gap="sm" wrap="nowrap">
            <Badge variant="light" color={user?.role === "TEACHER" ? "indigo" : "teal"} className="desktop-only">
              {user?.role === "TEACHER" ? "Giảng viên" : user?.role === "STUDENT" ? "Sinh viên" : user?.role}
            </Badge>
            <Avatar color="indigo" radius="xl" size={36}>{initials}</Avatar>
            <Box className="desktop-only">
              <Text size="sm" fw={600} lh={1.2} data-testid="current-user">{user?.full_name}</Text>
              <Text size="xs" c="dimmed">{user?.username}</Text>
            </Box>
            <Button variant="default" size="xs" onClick={() => void doLogout()}>{t.nav.logout}</Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar className="app-navbar" p="md">
        <AppShell.Section grow>
          <Text size="xs" fw={700} c="dimmed" tt="uppercase" px="sm" py="xs" lts="0.08em">Không gian làm việc</Text>
          <Stack gap={4} mt={6}>
            {links.map((item) => (
              <NavLink
                key={item.to}
                component={Link}
                to={item.to}
                label={item.label}
                description={item.caption}
                active={location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)}
                onClick={close}
                color="indigo"
                variant="light"
                style={{ borderRadius: 10 }}
              />
            ))}
          </Stack>
        </AppShell.Section>
        <AppShell.Section>
          <Divider mb="md" />
          <Box p="sm" bg="indigo.0" style={{ borderRadius: 12 }}>
            <Text size="xs" fw={700} c="indigo.8">SPNC Workspace</Text>
            <Text size="xs" c="dimmed" mt={3}>Dữ liệu được lưu tự động sau mỗi thao tác.</Text>
          </Box>
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main bg="#f5f7fb">
        <Box className="page-shell"><Outlet /></Box>
      </AppShell.Main>
    </AppShell>
  );
}

export function RoleHome() {
  const { user } = useAuth();
  if (user?.role === "STUDENT") return <Navigate to="/practice" replace />;
  if (user?.role === "TEACHER") return <Navigate to="/teacher/classes" replace />;
  return <Placeholder />;
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
