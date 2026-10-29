import { expect, test } from "@playwright/test";
import { applyEditorChanges, type EditorChangedPayload } from "../src/trace/payloads";
import {
  FINAL_PW,
  SUM_PY,
  TEMP_PW,
  adminToken,
  createUser,
  editorText,
  expectContiguous,
  latestSessionId,
  serverTrace,
  setupProblem,
  snapshotSource,
  typeInEditor,
  uiLogin,
  waitTraceFlushed,
  type ServerEvent,
} from "./helpers";

const replay = (events: ServerEvent[]) =>
  applyEditorChanges(
    "",
    events.filter((e) => e.event_type === "EDITOR_CHANGED").map((e) => e.payload as EditorChangedPayload),
  );

test("AC-20A-02: forced password change before anything else, then the student home", async ({ page }) => {
  const admin = await adminToken();
  const student = await createUser(admin, "STUDENT", false);
  await uiLogin(page, student.username, TEMP_PW);
  await expect(page).toHaveURL(/\/change-password$/);
  await page.goto("/practice");
  await expect(page).toHaveURL(/\/change-password$/);
  await page.getByLabel("Mật khẩu hiện tại").fill(TEMP_PW);
  await page.getByLabel(/^Mật khẩu mới/).fill(FINAL_PW);
  await page.getByLabel("Nhập lại mật khẩu mới").fill(FINAL_PW);
  await page.getByRole("button", { name: "Đổi mật khẩu" }).click();
  await expect(page).toHaveURL(/\/practice$/);
  await expect(page.getByTestId("current-user")).toContainText(student.username);
  // A reload keeps the session (refresh token, docs/46 D7)
  await page.reload();
  await expect(page.getByTestId("current-user")).toContainText(student.username);
});

test("AC-20A-07: open, edit, checkpoint, run, submit; the server trace is contiguous and complete", async ({ page }) => {
  const admin = await adminToken();
  const teacher = await createUser(admin, "TEACHER", true);
  const student = await createUser(admin, "STUDENT", true);
  const { problemId, classId } = await setupProblem(teacher, student);

  await uiLogin(page, student.username, FINAL_PW);
  await expect(page.getByTestId("problem-table")).toBeVisible();
  await page.goto(`/practice/problems/${problemId}`);
  await page.getByTestId("start-session").click();
  await typeInEditor(page, SUM_PY);
  // Checkpoint cadence comes from the server (TRACE_CHECKPOINT_INTERVAL_SECONDS, default 60 s)
  await page.waitForTimeout(65_000);
  await waitTraceFlushed(page);

  await page.getByLabel("Dữ liệu vào cho lần chạy").fill("1 2\n");
  await page.getByRole("button", { name: "Chạy thử" }).click();
  await expect(page.getByTestId("run-result")).toBeVisible({ timeout: 90_000 });

  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: "Nộp bài" }).click();
  await expect(page.getByTestId("submission-result")).toHaveAttribute("data-verdict", "ACCEPTED", { timeout: 120_000 });

  const sessionId = await latestSessionId(student, problemId);
  const events = await serverTrace(teacher, classId, student.id, sessionId);
  expectContiguous(events);
  const types = new Set(events.map((e) => e.event_type));
  for (const t of ["PROBLEM_OPENED", "EDITOR_CHANGED", "SESSION_CHECKPOINT", "RUN_REQUESTED", "RUN_COMPLETED", "SUBMISSION_CREATED"]) {
    expect(types, t).toContain(t);
  }
  expect(events[0]!.event_type).toBe("PROBLEM_OPENED");
  // Submit ends the session: the server appends SUBMISSION_CREATED then SESSION_ENDED (docs/46 F9)
  expect(events.slice(-2).map((e) => e.event_type)).toEqual(["SUBMISSION_CREATED", "SESSION_ENDED"]);
  // Replaying the EDITOR_CHANGED diffs reproduces exactly the code that was submitted
  const submitted = events.find((e) => e.event_type === "SUBMISSION_CREATED")!.payload.code_snapshot_id as string;
  const source = await snapshotSource(teacher, classId, student.id, sessionId, submitted);
  expect(replay(events)).toBe(source);
  expect(source.split("\n").map((l) => l.trimEnd()).join("\n").trimEnd()).toBe(SUM_PY.trimEnd());
});

test("AC-20A-08: edits made while ingest fails survive a reload with no gap and no duplicate", async ({ page }) => {
  const admin = await adminToken();
  const teacher = await createUser(admin, "TEACHER", true);
  const student = await createUser(admin, "STUDENT", true);
  const { problemId, classId } = await setupProblem(teacher, student);

  await uiLogin(page, student.username, FINAL_PW);
  await expect(page.getByTestId("current-user")).toBeVisible();
  await page.goto(`/practice/problems/${problemId}`);
  await page.getByTestId("start-session").click();
  await typeInEditor(page, "x = 1\n");
  await waitTraceFlushed(page);

  await page.route("**/trace-events/batch", (route) => route.abort("internetdisconnected"));
  await typeInEditor(page, "y = 2\n");
  await expect(page.getByTestId("trace-status")).toHaveAttribute("data-phase", "retrying");
  await page.waitForTimeout(1500); // draft write is throttled to 1 s
  await page.reload();
  await page.unroute("**/trace-events/batch");

  await waitTraceFlushed(page);
  const content = await editorText(page);
  expect(content).toContain("x = 1");
  expect(content).toContain("y = 2");

  // A run snapshots the restored editor content: the trace must replay to exactly that code
  await page.getByRole("button", { name: "Chạy thử" }).click();
  await expect(page.getByTestId("run-result")).toBeVisible({ timeout: 90_000 });
  await waitTraceFlushed(page);

  const sessionId = await latestSessionId(student, problemId);
  const events = await serverTrace(teacher, classId, student.id, sessionId);
  expectContiguous(events);
  const runAt = events.findIndex((e) => e.event_type === "RUN_REQUESTED");
  const runSnapshot = events[runAt]!.payload.code_snapshot_id as string;
  expect(replay(events.slice(0, runAt))).toBe(await snapshotSource(teacher, classId, student.id, sessionId, runSnapshot));
});

test("AC-20A-04/05: a teacher gets the placeholder; a student page shows the backend 403 with a request id", async ({ page }) => {
  const admin = await adminToken();
  const teacher = await createUser(admin, "TEACHER", true);
  await uiLogin(page, teacher.username, FINAL_PW);
  await expect(page.getByText("Chức năng đang được phát triển")).toBeVisible();
  await page.goto("/practice");
  const alert = page.getByTestId("error-alert");
  await expect(alert).toHaveAttribute("data-error-code", "FORBIDDEN_ROLE");
  await expect(alert.getByTestId("request-id")).not.toBeEmpty();
});
