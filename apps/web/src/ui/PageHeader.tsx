import { Box, Group, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: ReactNode; description?: string; action?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" gap="lg">
      <Box>
        {eyebrow && <Text size="xs" fw={700} c="indigo" tt="uppercase" lts="0.1em">{eyebrow}</Text>}
        <Title order={2} mt={eyebrow ? 4 : 0}>{title}</Title>
        {description && <Text c="dimmed" mt={6}>{description}</Text>}
      </Box>
      {action}
    </Group>
  );
}
