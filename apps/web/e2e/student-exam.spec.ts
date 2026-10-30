import { expect, request, test } from "@playwright/test";
import { adminToken, createUser, FINAL_PW, setupProblem, typeInEditor, uiLogin } from "./helpers";

test("AC-21B: student starts an assigned exam, works in the workspace and finalizes", async ({ page }) => {
  const admin = await adminToken();
  const teacher = await createUser(admin, "TEACHER", true);
  const student = await createUser(admin, "STUDENT", true);
  const { problemId, classId } = await setupProblem(teacher, student);
  const api = await request.newContext({ baseURL: process.env.SPNC_WEB_URL ?? "http://127.0.0.1:8080" });
  const bearer = { Authorization: `Bearer ${teacher.token}` };
  const startsAt = Date.now() + 15_000;
  const examTitle = `PW Student Exam ${Date.now()}`;
  const created = await api.post("/api/v1/exams", { data: {
    title: examTitle,
    start_time: new Date(startsAt).toISOString(),
    end_time: new Date(startsAt + 60 * 60_000).toISOString(),
    duration_minutes: 30,
    allow_view_result_after: true,
  }, headers: bearer });
  expect(created.status(), await created.text()).toBe(201);
  const examId = (await created.json()).id as string;
  const assigned = await api.post(`/api/v1/exams/${examId}/classes`, { data: { class_id: classId }, headers: bearer });
  expect(assigned.status(), await assigned.text()).toBeLessThan(300);
  const attached = await api.post(`/api/v1/exams/${examId}/problems`, { data: { problem_id: problemId, order_index: 1, max_score: 100 }, headers: bearer });
  expect(attached.status(), await attached.text()).toBeLessThan(300);
  const published = await api.post(`/api/v1/exams/${examId}/publish`, { headers: bearer });
  expect(published.status(), await published.text()).toBe(200);
  await api.dispose();

  await uiLogin(page, student.username, FINAL_PW);
  await expect(page.getByTestId("current-user")).toContainText(student.username);
  await page.goto("/student/exams");
  await expect(page.getByText(examTitle)).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  await page.getByRole("link", { name: "Chi tiết" }).last().click();
  await expect(page.getByRole("heading", { name: examTitle })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  await page.waitForTimeout(Math.max(0, startsAt - Date.now() + 250));
  await page.getByRole("button", { name: "Bắt đầu kỳ thi" }).click();
  await expect(page.getByText("Đang làm")).toBeVisible();
  await expect(page.getByText(/PW Sum/)).toBeVisible();
  await page.getByRole("link", { name: /Mở bài/ }).click();
  await page.getByRole("button", { name: "Bắt đầu làm đề" }).click();
  await expect(page.locator(".monaco-editor")).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  await typeInEditor(page, "a, b = map(int, input().split())\nprint(a + b)\n");
  await page.getByLabel("Dữ liệu vào cho lần chạy").fill("1 2\n");
  await page.getByRole("button", { name: "Chạy thử" }).click();
  await expect(page.getByTestId("run-result")).toBeVisible({ timeout: 30_000 });
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Nộp bài" }).click();
  await expect(page.getByText("Kết quả sẽ được công bố sau.")).toBeVisible({ timeout: 30_000 });
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Nộp và kết thúc kỳ thi" }).click();
  await expect(page.getByText("Trạng thái tham gia: COMPLETED")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});
