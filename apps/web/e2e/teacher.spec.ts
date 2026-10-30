import { expect, test, type Browser, type Page } from "@playwright/test";
import { FINAL_PW, SUM_PY, adminToken, createUser, setupProblem, typeInEditor, uiLogin, waitTraceFlushed } from "./helpers";

async function loggedIn(browser: Browser, username: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await uiLogin(page, username, FINAL_PW);
  await expect(page.getByTestId("current-user")).toContainText(username);
  return page;
}

test("AC-20B-01/02/03: teacher creates a class, the student joins with the code, the roster shows the name", async ({ browser }) => {
  const admin = await adminToken();
  const teacher = await createUser(admin, "TEACHER", true);
  const student = await createUser(admin, "STUDENT", true);

  const tp = await loggedIn(browser, teacher.username);
  await expect(tp).toHaveURL(/\/teacher\/classes$/);
  await tp.getByLabel("Tên lớp").fill("Lớp 10A1");
  await tp.getByRole("button", { name: "Tạo lớp" }).click();
  await tp.getByTestId("class-table").getByRole("link", { name: "Mở" }).click();
  const code = (await tp.getByTestId("invite-code").innerText()).trim();
  expect(code.length).toBeGreaterThan(3);

  const sp = await loggedIn(browser, student.username);
  await sp.goto("/classes");
  await sp.getByLabel("Mã tham gia").fill("WRONGCODE");
  await sp.getByRole("button", { name: "Tham gia lớp" }).click();
  await expect(sp.getByTestId("error-alert")).toHaveAttribute("data-error-code", "INVITE_CODE_INVALID");
  await sp.getByLabel("Mã tham gia").fill(code);
  await sp.getByRole("button", { name: "Tham gia lớp" }).click();
  await expect(sp.getByTestId("join-ok")).toBeVisible();
  await expect(sp.getByTestId("my-class-table")).toContainText("Lớp 10A1");

  await tp.reload();
  await tp.getByRole("tab", { name: "Học sinh" }).click();
  await expect(tp.getByTestId("roster-table")).toContainText(student.username);
});

test("AC-20B-06/07/08/10: replay matches every snapshot; a signal is acknowledged; a note is added", async ({ browser }) => {
  const admin = await adminToken();
  const teacher = await createUser(admin, "TEACHER", true);
  const student = await createUser(admin, "STUDENT", true);
  const { problemId, classId } = await setupProblem(teacher, student);

  // Student: the statement appears only after the session starts (D7)
  const sp = await loggedIn(browser, student.username);
  await sp.goto(`/practice/problems/${problemId}`);
  await expect(sp.getByTestId("problem-statement")).toHaveCount(0);
  await sp.getByTestId("start-session").click();
  await expect(sp.getByTestId("problem-statement")).toBeVisible();
  await typeInEditor(sp, SUM_PY); // within 30 s of the statement appearing: FAST_FIRST_CODE
  await sp.getByLabel("Dữ liệu vào cho lần chạy").fill("1 2\n");
  await sp.getByRole("button", { name: "Chạy thử" }).click();
  await expect(sp.getByTestId("run-result")).toBeVisible({ timeout: 90_000 });
  await waitTraceFlushed(sp);

  // Teacher: the student shows up as needing attention once the signal scheduler (60 s cycle)
  // evaluates the still ACTIVE session; FAST_FIRST_CODE is evaluated for ACTIVE sessions only
  const tp = await loggedIn(browser, teacher.username);
  await tp.goto(`/teacher/classes/${classId}`);
  await expect(async () => {
    await tp.reload();
    await expect(tp.getByTestId("attention-table")).toContainText(student.username, { timeout: 2_000 });
  }).toPass({ timeout: 150_000, intervals: [3_000] });

  sp.once("dialog", (d) => void d.accept());
  await sp.getByRole("button", { name: "Nộp bài" }).click();
  await expect(sp.getByTestId("submission-result")).toHaveAttribute("data-verdict", "ACCEPTED", { timeout: 120_000 });

  await tp.getByTestId("attention-table").getByRole("link", { name: "Xem" }).click();
  await tp.getByTestId("session-table").getByRole("link", { name: "Xem" }).first().click();

  // Replay: every snapshot (RUN, SUBMIT) verified, none mismatched
  const verification = tp.getByTestId("replay-verification");
  await expect(verification).toHaveAttribute("data-mismatch", "0", { timeout: 60_000 });
  await expect(async () => expect(Number(await verification.getAttribute("data-checked"))).toBeGreaterThanOrEqual(2)).toPass({ timeout: 30_000 });
  await tp.locator('[data-testid="snapshot-marker"][data-event-type="SUBMISSION_CREATED"]').click();
  await expect(tp.getByTestId("point-verification")).toHaveAttribute("data-status", "match");

  // Signal: neutral text, acknowledge it
  const card = tp.locator('[data-testid="signal-card"][data-signal-type="FAST_FIRST_CODE"]').first();
  await expect(card).toContainText("Bắt đầu gõ code");
  await card.getByRole("button", { name: "Ghi nhận" }).click();
  await expect(card).toHaveAttribute("data-status", "ACKNOWLEDGED");

  // Annotation on this session
  await tp.getByPlaceholder("Ghi chú của bạn (chỉ bạn xem được)").fill("Đã trao đổi với học sinh.");
  await tp.getByRole("button", { name: "Thêm ghi chú" }).click();
  await expect(tp.getByTestId("annotation").first()).toContainText("Đã trao đổi với học sinh.");
});

test("AC-20B-09: a student's run reaches the open teacher page live, without reload", async ({ browser }) => {
  const admin = await adminToken();
  const teacher = await createUser(admin, "TEACHER", true);
  const student = await createUser(admin, "STUDENT", true);
  const { problemId, classId } = await setupProblem(teacher, student);

  const sp = await loggedIn(browser, student.username);
  await sp.goto(`/practice/problems/${problemId}`);
  await sp.getByTestId("start-session").click();
  await typeInEditor(sp, "print(1)\n");
  await waitTraceFlushed(sp);

  const tp = await loggedIn(browser, teacher.username);
  await tp.goto(`/teacher/classes/${classId}/students/${student.id}`);
  await tp.getByTestId("session-table").getByRole("link", { name: "Xem" }).first().click();
  await expect(tp.getByTestId("live-status")).toHaveAttribute("data-status", "live");
  await expect(tp.getByTestId("run-item")).toHaveCount(0);

  await sp.getByRole("button", { name: "Chạy thử" }).click();
  await expect(sp.getByTestId("run-result")).toBeVisible({ timeout: 90_000 });
  // run.completed arrives over the socket; well before the 15 s refresh of an ACTIVE session
  await expect(tp.locator('[data-testid="run-item"][data-status="COMPLETED"]')).toHaveCount(1, { timeout: 8_000 });
});
