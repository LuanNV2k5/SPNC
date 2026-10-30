import { Badge, Box, Button, Center, Checkbox, Group, Loader, NumberInput, Pagination, Paper, Select, SimpleGrid, Stack, Table, Text, Textarea, TextInput, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { PageHeader } from "../../ui/PageHeader";
import { listClasses, listExams, keys, createExam, getExam, updateExam, listExamClasses, assignExamClass, unassignExamClass, listExamProblems, attachExamProblem, detachExamProblem, publishExam, cancelExam, getExamObservation } from "./teacherApi";
import { listProblems } from "./problemApi";

const statusText: Record<string, string> = { DRAFT: "Bản nháp", SCHEDULED: "Đã lên lịch", ONGOING: "Đang diễn ra", ENDED: "Đã kết thúc", CANCELLED: "Đã hủy" };
const localDate = (value: string) => { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };
const isoDate = (value: string) => new Date(value).toISOString();

export function ExamsPage() {
  const { examId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const isNew = examId === "new";
  const exams = useQuery({ queryKey: keys.exams(), queryFn: listExams, enabled: !examId });
  const exam = useQuery({ queryKey: keys.exam(examId ?? ""), queryFn: () => getExam(examId!), enabled: !!examId && !isNew });
  const classes = useQuery({ queryKey: keys.classes(), queryFn: listClasses, enabled: !!examId && !isNew });
  const assigned = useQuery({ queryKey: keys.examClasses(examId ?? ""), queryFn: () => listExamClasses(examId!), enabled: !!examId && !isNew });
  const examProblems = useQuery({ queryKey: keys.examProblems(examId ?? ""), queryFn: () => listExamProblems(examId!), enabled: !!examId && !isNew });
  const problems = useQuery({ queryKey: ["t", "problems", "exam-picker"], queryFn: () => listProblems({ page: 1 }) , enabled: !!examId && !isNew });
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [duration, setDuration] = useState<number | string>(90);
  const [viewResults, setViewResults] = useState(false);
  const [classId, setClassId] = useState<string | null>(null);
  const [problemId, setProblemId] = useState<string | null>(null);
  const [maxScore, setMaxScore] = useState<number | string>(100);
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!exam.data) return;
    setTitle(exam.data.title); setDescription(exam.data.description ?? "");
    setStart(localDate(exam.data.start_time)); setEnd(localDate(exam.data.end_time));
    setDuration(exam.data.duration_minutes ?? 90); setViewResults(exam.data.allow_view_result_after);
  }, [exam.data]);

  const refresh = () => { void qc.invalidateQueries({ queryKey: keys.exams() }); if (examId && !isNew) { void qc.invalidateQueries({ queryKey: keys.exam(examId) }); void qc.invalidateQueries({ queryKey: keys.examClasses(examId) }); void qc.invalidateQueries({ queryKey: keys.examProblems(examId) }); void qc.invalidateQueries({ queryKey: ["t", "exam-observation", examId] }); } };
  const save = useMutation({ mutationFn: () => isNew ? createExam({ title, description: description || null, start_time: isoDate(start), end_time: isoDate(end), duration_minutes: Number(duration) || null, allow_view_result_after: viewResults }) : updateExam(examId!, { title, description, start_time: isoDate(start), end_time: isoDate(end), duration_minutes: Number(duration) || null, allow_view_result_after: viewResults }), onSuccess: (saved) => { refresh(); if (isNew) navigate(`/teacher/exams/${saved.id}`, { replace: true }); } });
  const attachClass = useMutation({ mutationFn: () => assignExamClass(examId!, classId!), onSuccess: () => { setClassId(null); refresh(); } });
  const removeClass = useMutation({ mutationFn: (id: string) => unassignExamClass(examId!, id), onSuccess: refresh });
  const attachProblem = useMutation({ mutationFn: () => attachExamProblem(examId!, problemId!, examProblems.data?.length ?? 0, Number(maxScore)), onSuccess: () => { setProblemId(null); refresh(); } });
  const removeProblem = useMutation({ mutationFn: (id: string) => detachExamProblem(examId!, id), onSuccess: refresh });
  const publish = useMutation({ mutationFn: () => publishExam(examId!), onSuccess: refresh });
  const cancel = useMutation({ mutationFn: (reason: string) => cancelExam(examId!, reason), onSuccess: refresh });
  const observation = useQuery({ queryKey: keys.examObservation(examId ?? "", page), queryFn: () => getExamObservation(examId!, page), enabled: !!examId && !isNew });
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate(); };

  if (!examId) return <Stack gap="lg"><PageHeader eyebrow="Không gian giảng viên" title="Kỳ thi" description="Lập lịch thi, chọn lớp và đề bài, theo dõi tình trạng tham gia." /><Group justify="flex-end"><Button component={Link} to="/teacher/exams/new">Tạo kỳ thi</Button></Group><ErrorAlert error={exams.error} />{exams.isPending && <Center py="xl"><Loader /></Center>}{exams.data && exams.data.items.length === 0 && <Paper className="surface-card" p="xl"><Stack align="center"><Text fw={700}>Chưa có kỳ thi</Text><Button component={Link} to="/teacher/exams/new">Tạo kỳ thi đầu tiên</Button></Stack></Paper>}{!!exams.data?.items.length && <Paper className="surface-card"><Table.ScrollContainer minWidth={700}><Table highlightOnHover><Table.Thead><Table.Tr><Table.Th>Tên kỳ thi</Table.Th><Table.Th>Thời gian</Table.Th><Table.Th>Trạng thái</Table.Th><Table.Th /></Table.Tr></Table.Thead><Table.Tbody>{exams.data.items.map((item) => <Table.Tr key={item.id}><Table.Td><Text fw={600}>{item.title}</Text><Text size="xs" c="dimmed">{item.description}</Text></Table.Td><Table.Td>{new Date(item.start_time).toLocaleString("vi-VN")}<Text size="xs" c="dimmed">đến {new Date(item.end_time).toLocaleString("vi-VN")}</Text></Table.Td><Table.Td><Badge>{statusText[item.status] ?? item.status}</Badge></Table.Td><Table.Td><Button component={Link} to={`/teacher/exams/${item.id}`} variant="light" size="xs">Quản lý</Button></Table.Td></Table.Tr>)}</Table.Tbody></Table></Table.ScrollContainer></Paper>}</Stack>;

  const canConfigure = isNew || exam.data?.status === "DRAFT";
  const classesById = new Map((classes.data?.items ?? []).map((item) => [item.id, item.name]));
  const problemsById = new Map((problems.data?.items ?? []).map((item) => [item.id, item.title]));
  return <Stack gap="lg"><Group justify="space-between"><Box><Text size="xs" fw={700} c="indigo" tt="uppercase">Không gian giảng viên</Text><Title order={2} mt={4}>{isNew ? "Tạo kỳ thi" : exam.data?.title ?? "Kỳ thi"}</Title></Box><Button component={Link} to="/teacher/exams" variant="default">Danh sách kỳ thi</Button></Group>
    {!isNew && exam.isPending && <Center py="xl"><Loader /></Center>}<ErrorAlert error={exam.error} />
    {(isNew || exam.data) && <Paper className="surface-card" p="lg"><form onSubmit={submit}><Stack><Text fw={700}>{isNew ? "Thông tin kỳ thi" : "Cấu hình kỳ thi"}</Text><SimpleGrid cols={{ base: 1, sm: 2 }}><TextInput label="Tên kỳ thi" value={title} onChange={(e) => setTitle(e.currentTarget.value)} required disabled={!canConfigure} /><NumberInput label="Thời lượng (phút)" value={duration} onChange={setDuration} min={1} disabled={!canConfigure} /><TextInput label="Bắt đầu" type="datetime-local" value={start} onChange={(e) => setStart(e.currentTarget.value)} required disabled={!canConfigure} /><TextInput label="Kết thúc" type="datetime-local" value={end} onChange={(e) => setEnd(e.currentTarget.value)} required disabled={!canConfigure} /></SimpleGrid><Textarea label="Mô tả" value={description} onChange={(e) => setDescription(e.currentTarget.value)} disabled={!canConfigure} /><Checkbox label="Cho phép sinh viên xem kết quả sau kỳ thi" checked={viewResults} onChange={(e) => setViewResults(e.currentTarget.checked)} disabled={!canConfigure} />{canConfigure && <Button type="submit" loading={save.isPending}>{isNew ? "Tạo kỳ thi" : "Lưu cấu hình"}</Button>}<ErrorAlert error={save.error} />{!isNew && <Text size="sm" c="dimmed">Trạng thái: {statusText[exam.data?.status ?? ""] ?? exam.data?.status}</Text>}</Stack></form></Paper>}
    {!isNew && exam.data && <>
      <Paper className="surface-card" p="lg"><Text fw={700} mb="sm">Lớp tham gia</Text><Group align="end"><Select style={{ flex: 1 }} label="Chọn lớp" placeholder="Lớp của bạn" value={classId} onChange={setClassId} data={(classes.data?.items ?? []).map((item) => ({ value: item.id, label: `${item.name} · ${item.academic_year}` }))} disabled={!canConfigure} /><Button onClick={() => attachClass.mutate()} disabled={!classId || !canConfigure} loading={attachClass.isPending}>Gắn lớp</Button></Group>{assigned.data?.map((item) => <Group key={item.class_id} justify="space-between" mt="sm"><Text>{classesById.get(item.class_id) ?? item.class_id}</Text>{canConfigure && <Button size="xs" color="red" variant="subtle" onClick={() => removeClass.mutate(item.class_id)}>Gỡ</Button>}</Group>)}<ErrorAlert error={attachClass.error ?? removeClass.error} /></Paper>
      <Paper className="surface-card" p="lg"><Text fw={700} mb="sm">Đề bài và điểm tối đa</Text><SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm"><Select label="Đề bài" placeholder="Chọn đề" value={problemId} onChange={setProblemId} data={(problems.data?.items ?? []).map((item) => ({ value: item.id, label: item.title }))} disabled={!canConfigure} /><NumberInput label="Điểm" value={maxScore} onChange={setMaxScore} min={1} disabled={!canConfigure} /><Button onClick={() => attachProblem.mutate()} disabled={!problemId || !canConfigure} loading={attachProblem.isPending} fullWidth>Thêm đề</Button></SimpleGrid>{examProblems.data?.map((item) => <Group key={item.problem_id} justify="space-between" mt="sm"><Text>{problemsById.get(item.problem_id) ?? item.problem_id}<Text span c="dimmed"> · {item.max_score} điểm</Text></Text>{canConfigure && <Button size="xs" color="red" variant="subtle" onClick={() => removeProblem.mutate(item.problem_id)}>Gỡ</Button>}</Group>)}<ErrorAlert error={attachProblem.error ?? removeProblem.error} /></Paper>
      <Paper className="surface-card" p="lg"><Group justify="space-between"><Box><Text fw={700}>Vòng đời kỳ thi</Text><Text size="sm" c="dimmed">Chỉ phát hành khi đã có ít nhất một lớp và một đề đủ bộ kiểm thử.</Text></Box><Group>{exam.data.status === "DRAFT" && <Button onClick={() => publish.mutate()} loading={publish.isPending}>Phát hành</Button>}{["DRAFT", "SCHEDULED"].includes(exam.data.status) && <Button color="red" variant="light" onClick={() => { const reason = window.prompt("Lý do hủy kỳ thi:"); if (reason?.trim()) cancel.mutate(reason.trim()); }}>Hủy kỳ thi</Button>}</Group></Group><ErrorAlert error={publish.error ?? cancel.error} />{exam.data.cancel_reason && <Text mt="sm" size="sm">Lý do hủy: {exam.data.cancel_reason}</Text>}</Paper>
      <Paper className="surface-card" p="lg"><Text fw={700} mb="sm">Tình trạng sinh viên</Text><ErrorAlert error={observation.error} />{observation.isPending ? <Loader size="sm" /> : <><Table.ScrollContainer minWidth={700}><Table><Table.Thead><Table.Tr><Table.Th>Sinh viên</Table.Th><Table.Th>Trạng thái</Table.Th><Table.Th>Đề đã nộp</Table.Th><Table.Th>Tín hiệu</Table.Th><Table.Th>Bắt đầu</Table.Th></Table.Tr></Table.Thead><Table.Tbody>{observation.data?.items.map((item) => <Table.Tr key={item.student_id}><Table.Td>{item.full_name}<Text size="xs" c="dimmed">{item.username}</Text></Table.Td><Table.Td>{item.participation_status}</Table.Td><Table.Td>{item.submitted_problem_count}</Table.Td><Table.Td>{item.signal_count}</Table.Td><Table.Td>{item.started_at ? new Date(item.started_at).toLocaleString("vi-VN") : "—"}</Table.Td></Table.Tr>)}</Table.Tbody></Table></Table.ScrollContainer>{observation.data && observation.data.total > 20 && <Pagination mt="md" total={Math.ceil(observation.data.total / 20)} value={page} onChange={setPage} />}{observation.data?.items.length === 0 && <Text size="sm" c="dimmed">Chưa có sinh viên tham gia.</Text>}</>}</Paper>
    </>}
  </Stack>;
}
