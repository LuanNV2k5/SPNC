import { Badge, Box, Button, Center, Code, Group, Loader, Paper, SegmentedControl, Stack, Text, Title, TypographyStylesProvider } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "../../api/errors";
import { useAuth } from "../auth/AuthContext";
import { Workspace } from "../practice/Workspace";
import { getTraceStore } from "../practice/traceStore";
import { participantDeadline } from "./deadline";
import { ErrorAlert } from "../../ui/ErrorAlert";
import { listExams, getParticipation, startParticipation, listExamProblems, startExamSession, finalizeExam } from "./studentExamApi";

export function StudentExamPage() {
  const { examId = "", problemId } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [language, setLanguage] = useState<string | null>(null);
  const [session, setSession] = useState<Awaited<ReturnType<typeof startExamSession>> | null>(null);
  const [sessionContent, setSessionContent] = useState("");
  const [sessionError, setSessionError] = useState<unknown>(null);
  const [now, setNow] = useState(Date.now());
  const exams = useQuery({ queryKey: ["student-exams"], queryFn: listExams });
  const participation = useQuery({ queryKey: ["student-exam-participation", examId], queryFn: () => getParticipation(examId), retry: false });
  const active = participation.data?.status === "IN_PROGRESS";
  const problems = useQuery({ queryKey: ["student-exam-problems", examId], queryFn: () => listExamProblems(examId), enabled: active });
  const exam = exams.data?.items.find((item) => item.id === examId);
  const selected = problems.data?.items.find((item) => item.id === problemId);
  const start = useMutation({ mutationFn: () => startParticipation(examId), onSuccess: () => qc.invalidateQueries({ queryKey: ["student-exam-participation", examId] }) });
  const finalize = useMutation({ mutationFn: () => finalizeExam(examId), onSuccess: async () => { setSession(null); await Promise.all([qc.invalidateQueries({ queryKey: ["student-exam-participation", examId] }), qc.invalidateQueries({ queryKey: ["student-exam-problems", examId] })]); } });
  const deadline = exam && participation.data ? participantDeadline(exam, participation.data) : null;
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const remaining = deadline == null ? null : Math.max(0, Math.floor((deadline - now) / 1000));

  const openProblem = async (id: string) => {
    if (!participation.data || !problems.data) return;
    const problem = problems.data.items.find((item) => item.id === id);
    const chosen = language ?? problem?.supported_languages[0];
    if (!chosen) return;
    setLanguage(chosen);
    setSessionError(null);
    try {
      const opened = await startExamSession(participation.data.id, id, chosen);
      const draft = await (await getTraceStore()).getDraft(opened.id);
      setSessionContent(draft?.content ?? "");
      setSession(opened);
    } catch (error) {
      setSessionError(error);
      await qc.invalidateQueries({ queryKey: ["student-exam-participation", examId] });
    }
  };

  if (exams.isPending || participation.isPending) return <Center py={80}><Loader /></Center>;
  return (
    <Stack gap="md">
      <Button component={Link} to="/student/exams" variant="subtle" size="compact-sm" w="fit-content">← Danh sách kỳ thi</Button>
      <ErrorAlert error={exams.error ?? (participation.error && (!(participation.error instanceof ApiError) || participation.error.status !== 404) ? participation.error : null)} />
      {!exam ? <Paper p="lg"><Text>Kỳ thi không tồn tại hoặc không còn được cấp cho tài khoản.</Text></Paper> : <>
        <Paper className="surface-card" p="lg"><Group justify="space-between" align="flex-start"><Box><Text size="xs" c="dimmed">KỲ THI</Text><Title order={2}>{exam.title}</Title>{exam.description && <Text mt="xs">{exam.description}</Text>}<Text size="sm" c="dimmed" mt="sm">{new Date(exam.start_time).toLocaleString("vi-VN")} – {new Date(exam.end_time).toLocaleString("vi-VN")}</Text></Box><Badge>{exam.status}</Badge></Group>
          {active && <Group mt="md"><Badge color="teal">Đang làm</Badge>{remaining !== null && <Text size="sm">Thời gian còn lại (ước tính): {Math.floor(remaining / 3600).toString().padStart(2, "0")}:{Math.floor((remaining % 3600) / 60).toString().padStart(2, "0")}:{(remaining % 60).toString().padStart(2, "0")}</Text>}</Group>}
          {!active && !participation.data && <Button mt="md" onClick={() => start.mutate()} loading={start.isPending} disabled={exam.status === "CANCELLED" || exam.status === "ENDED"}>Bắt đầu kỳ thi</Button>}
          {!active && participation.data && <Text mt="md" c="dimmed">Trạng thái tham gia: {participation.data.status}</Text>}
          {active && <Button mt="md" color="red" variant="light" onClick={() => { if (window.confirm("Kết thúc kỳ thi? Các phiên đang mở sẽ kết thúc; không tạo bài nộp tự động.")) finalize.mutate(); }} loading={finalize.isPending}>Nộp và kết thúc kỳ thi</Button>}
          <ErrorAlert error={start.error ?? finalize.error} />
        </Paper>
        {active && <>
          <Group align="flex-start"><Box style={{ flex: 1 }}><ErrorAlert error={problems.error} /></Box>{problems.error && <Button variant="default" onClick={() => void problems.refetch()}>Tải lại đề</Button>}</Group>
          {problems.isPending && <Loader size="sm" />}
          {problems.data?.items.map((problem) => <Paper key={problem.id} p="md" className="surface-card"><Group justify="space-between"><Box><Text fw={600}>{problem.order_index}. {problem.title}</Text><Text size="sm" c="dimmed">Tối đa {problem.max_score} điểm · {problem.time_limit_ms} ms · {problem.memory_limit_mb} MB</Text></Box><Button component={Link} to={`/student/exams/${examId}/problems/${problem.id}`} onClick={() => { setSession(null); setSessionContent(""); }} variant={problemId === problem.id ? "filled" : "light"}>Mở bài</Button></Group></Paper>)}
          {problemId && selected && <Paper p="lg" className="surface-card"><Stack gap="md"><Group justify="space-between"><Title order={3}>{selected.title}</Title><Button component={Link} to={`/student/exams/${examId}`} variant="subtle" onClick={() => { setSession(null); setSessionContent(""); }}>Đóng bài</Button></Group>
            <ErrorAlert error={sessionError} />
            <Box><Text fw={600}>Đề bài</Text><TypographyStylesProvider><Text style={{ whiteSpace: "pre-wrap" }}>{selected.description}</Text></TypographyStylesProvider></Box>
            {selected.input_format && <Box><Text fw={600}>Dữ liệu vào</Text><Text style={{ whiteSpace: "pre-wrap" }}>{selected.input_format}</Text></Box>}{selected.output_format && <Box><Text fw={600}>Dữ liệu ra</Text><Text style={{ whiteSpace: "pre-wrap" }}>{selected.output_format}</Text></Box>}{selected.constraints && <Box><Text fw={600}>Ràng buộc</Text><Text style={{ whiteSpace: "pre-wrap" }}>{selected.constraints}</Text></Box>}
            {selected.samples.map((sample) => <Group key={sample.order_index} grow><Code block>{sample.input_data}</Code><Code block>{sample.expected_output}</Code></Group>)}
            {!session && <Group><SegmentedControl value={language ?? selected.supported_languages[0] ?? ""} onChange={setLanguage} data={selected.supported_languages.map((item) => ({ value: item, label: item }))} /><Button onClick={() => void openProblem(selected.id)}>Bắt đầu làm đề</Button></Group>}
            {session && user && <Workspace key={session.id} session={session} userId={user.id} initialContent={sessionContent} onClosed={() => setSession(null)} />}
          </Stack></Paper>}
        </>}
      </>}
    </Stack>
  );
}
