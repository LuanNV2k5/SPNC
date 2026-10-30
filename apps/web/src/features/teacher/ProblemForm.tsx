import { Box, Button, Checkbox, Divider, Grid, Group, NumberInput, Paper, Select, Stack, Text, TextInput, Textarea, Title } from "@mantine/core";
import { useState, type FormEvent } from "react";
import { difficultyLabel, languageLabel, tt } from "../../i18n/vi";
import { type Language, type ProblemDraft, type Visibility, validateProblemDraft } from "./problemDraft";

interface Props {
  initial: ProblemDraft;
  submitLabel: string;
  pending: boolean;
  onSubmit: (draft: ProblemDraft) => void;
}

const visibilityOptions = [
  { value: "PRIVATE", label: tt.problems.visibility.PRIVATE },
  { value: "CLASS", label: tt.problems.visibility.CLASS },
  { value: "PUBLIC", label: tt.problems.visibility.PUBLIC },
];

export function ProblemForm({ initial, submitLabel, pending, onSubmit }: Props) {
  const [draft, setDraft] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = <K extends keyof ProblemDraft>(key: K, value: ProblemDraft[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next = validateProblemDraft(draft);
    setErrors(next);
    if (Object.keys(next).length === 0) onSubmit(draft);
  };

  return (
    <form onSubmit={submit}>
      <Grid align="flex-start" gutter="xl">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Stack gap="lg">
            <Paper className="surface-card" p={{ base: "md", sm: "xl" }}>
              <Title order={4}>Nội dung bài tập</Title>
              <Text size="sm" c="dimmed" mt={4} mb="lg">Viết rõ yêu cầu và định dạng để học sinh có thể bắt đầu mà không cần giải thích thêm.</Text>
              <Stack>
          <TextInput
            name="problem_title"
            label={tt.problems.fields.title}
            value={draft.title}
            onChange={(e) => set("title", e.currentTarget.value)}
            error={errors.title}
            required
          />
          <Textarea
            name="problem_description"
            label={tt.problems.fields.description}
            value={draft.description}
            onChange={(e) => set("description", e.currentTarget.value)}
            error={errors.description}
            minRows={7}
            autosize
            required
          />
                <Divider label="Đặc tả dữ liệu" labelPosition="left" my="sm" />
                <Textarea label={tt.problems.fields.inputFormat} description="Mỗi dòng chứa gì, thứ tự các giá trị ra sao?" value={draft.inputFormat} onChange={(e) => set("inputFormat", e.currentTarget.value)} minRows={3} autosize />
                <Textarea label={tt.problems.fields.outputFormat} description="Kết quả cần in và quy tắc định dạng." value={draft.outputFormat} onChange={(e) => set("outputFormat", e.currentTarget.value)} minRows={3} autosize />
                <Textarea label={tt.problems.fields.constraints} description="Giới hạn của dữ liệu để định hướng thuật toán." value={draft.constraints} onChange={(e) => set("constraints", e.currentTarget.value)} minRows={3} autosize />
              </Stack>
            </Paper>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Stack gap="lg">
            <Paper className="surface-card" p="lg">
              <Title order={4}>Thiết lập chấm bài</Title>
              <Text size="sm" c="dimmed" mt={4} mb="lg">Cấu hình cách đề xuất hiện và giới hạn thực thi.</Text>
              <Stack>
          <Grid>
            <Grid.Col span={{ base: 12 }}>
              <Select
                label={tt.problems.fields.difficulty}
                clearable
                value={draft.difficulty || null}
                onChange={(value) => set("difficulty", (value ?? "") as ProblemDraft["difficulty"])}
                data={Object.entries(difficultyLabel).map(([value, label]) => ({ value, label }))}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12 }}>
              <Select
                label={tt.problems.fields.visibility}
                value={draft.visibility}
                onChange={(value) => value && set("visibility", value as Visibility)}
                data={visibilityOptions}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 6 }}>
              <NumberInput
                label={tt.problems.fields.timeLimit}
                value={draft.timeLimitMs}
                onChange={(value) => set("timeLimitMs", Number(value) || 0)}
                error={errors.timeLimitMs}
                min={1}
                suffix=" ms"
              />
            </Grid.Col>
            <Grid.Col span={{ base: 6 }}>
              <NumberInput
                label={tt.problems.fields.memoryLimit}
                value={draft.memoryLimitMb}
                onChange={(value) => set("memoryLimitMb", Number(value) || 0)}
                error={errors.memoryLimitMb}
                min={1}
                suffix=" MB"
              />
            </Grid.Col>
          </Grid>
          <Box>
            <Text size="sm" fw={500} mb={6}>{tt.problems.fields.languages}</Text>
            <Checkbox.Group value={draft.languages} onChange={(value) => set("languages", value as Language[])}>
              <Group>
                <Checkbox value="CPP17" label={languageLabel.CPP17} />
                <Checkbox value="PYTHON3" label={languageLabel.PYTHON3} />
              </Group>
            </Checkbox.Group>
            {errors.languages && <Text c="red" size="xs" mt={4}>{errors.languages}</Text>}
          </Box>
              </Stack>
            </Paper>
            <Paper p="md" bg="indigo.0" style={{ border: "1px solid var(--mantine-color-indigo-1)" }}>
              <Text size="sm" fw={700} c="indigo.9">Gợi ý trước khi lưu</Text>
              <Text size="sm" c="indigo.8" mt={5}>Bạn có thể để đề ở chế độ Riêng tư trong lúc hoàn thiện testcase.</Text>
            </Paper>
          </Stack>
        </Grid.Col>
      </Grid>
      <Group justify="space-between" className="sticky-save">
        <Text size="sm" c="dimmed">Kiểm tra các trường bắt buộc trước khi tiếp tục.</Text>
        <Button type="submit" loading={pending} data-testid="save-problem" size="md">{submitLabel}</Button>
      </Group>
    </form>
  );
}
