import { expect, test, type Browser, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { adminToken, createUser, FINAL_PW, setupProblem, uiLogin } from "./helpers";

async function loggedIn(browser: Browser, username: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await uiLogin(page, username, FINAL_PW);
  await expect(page.getByTestId("current-user")).toContainText(username);
  return page;
}

function localDateTime(offsetMs: number) {
  const date = new Date(Date.now() + offsetMs);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

test("AC-21A-01: teacher creates, configures and publishes an exam, then observes the student", async ({ browser }) => {
  const admin = await adminToken();
  const teacher = await createUser(admin, "TEACHER", true);
  const student = await createUser(admin, "STUDENT", true);
  const { problemTitle } = await setupProblem(teacher, student);
  const title = `PW Exam ${Date.now()}`;

  const page = await loggedIn(browser, teacher.username);
  await page.goto("/teacher/exams/new");
  await page.getByLabel("Tên kỳ thi").fill(title);
  await page.getByLabel("Thời lượng (phút)").fill("60");
  await page.getByLabel("Bắt đầu").fill(localDateTime(24 * 60 * 60 * 1000));
  await page.getByLabel("Kết thúc").fill(localDateTime(26 * 60 * 60 * 1000));
  await page.getByLabel("Mô tả").fill("Kỳ thi tích hợp được tạo từ giao diện quản lý.");
  await page.getByLabel("Cho phép sinh viên xem kết quả sau kỳ thi").check();
  await page.getByRole("button", { name: "Tạo kỳ thi" }).click();
  await expect(page).toHaveURL(/\/teacher\/exams\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: title })).toBeVisible();

  await page.getByRole("textbox", { name: "Chọn lớp" }).click();
  await page.getByRole("option", { name: /PW ·/ }).click();
  await page.getByRole("button", { name: "Gắn lớp" }).click();
  await expect(page.getByText("PW", { exact: true })).toBeVisible();

  await page.getByRole("textbox", { name: "Đề bài" }).click();
  await page.getByRole("option", { name: problemTitle }).click();
  await page.getByLabel("Điểm").fill("50");
  await page.getByRole("button", { name: "Thêm đề" }).click();
  await expect(page.getByText(`${problemTitle} · 50 điểm`)).toBeVisible();

  await page.getByRole("button", { name: "Phát hành" }).click();
  await expect(page.getByText("Trạng thái: Đã lên lịch")).toBeVisible();
  await expect(page.getByRole("button", { name: "Hủy kỳ thi" })).toBeVisible();
  await expect(page.getByText(student.username)).toBeVisible();
  await expect(page.getByText("NOT_STARTED")).toBeVisible();

  const reviewDir = process.env.SPNC_REVIEW_DIR;
  if (reviewDir) {
    await mkdir(reviewDir, { recursive: true });
    await page.screenshot({ path: join(reviewDir, "exam-detail-desktop.png"), fullPage: true });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  if (reviewDir) await page.screenshot({ path: join(reviewDir, "exam-detail-mobile.png"), fullPage: true });
  const mobileProblemPicker = await page.getByRole("textbox", { name: "Đề bài" }).boundingBox();
  expect(mobileProblemPicker?.width ?? 0).toBeGreaterThan(220);
  await expect(page.getByRole("button", { name: "Mở điều hướng" })).toBeVisible();
  await page.getByRole("button", { name: "Mở điều hướng" }).click();
  await page.getByRole("link", { name: /Kỳ thi/ }).click();
  await expect(page).toHaveURL(/\/teacher\/exams$/);
  await expect(page.getByText(title)).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  if (reviewDir) await page.screenshot({ path: join(reviewDir, "exam-list-mobile.png"), fullPage: true });
  await page.getByRole("link", { name: "Quản lý" }).click();
  await expect(page).toHaveURL(/\/teacher\/exams\/[0-9a-f-]+$/);
});
