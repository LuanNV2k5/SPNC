import { expect, request, type APIRequestContext, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

/** API setup through the same origin as the browser (`/api` is proxied by the web service). */

const API = "/api/v1";
export const TEMP_PW = "Temp-Pw-2026!";
export const FINAL_PW = "Final-Pw-2026!";
export const SUM_PY = "a, b = map(int, input().split())\nprint(a + b)\n";

export interface Person {
  id: string;
  username: string;
  token: string;
}

async function ctx(): Promise<APIRequestContext> {
  return request.newContext({ baseURL: process.env.SPNC_WEB_URL ?? "http://127.0.0.1:8080" });
}

async function login(api: APIRequestContext, username: string, password: string) {
  return api.post(`${API}/auth/login`, { form: { username, password } });
}

const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });

async function readyUser(api: APIRequestContext, username: string, temp: string, final: string): Promise<string> {
  const r = await login(api, username, temp);
  expect(r.status(), await r.text()).toBe(200);
  const token = (await r.json()).access_token as string;
  const c = await api.post(`${API}/auth/change-password`, { data: { current_password: temp, new_password: final }, headers: bearer(token) });
  expect(c.status(), await c.text()).toBe(200);
  const again = await login(api, username, final);
  return (await again.json()).access_token as string;
}

export async function adminToken(): Promise<string> {
  const api = await ctx();
  const user = process.env.SPNC_E2E_ADMIN_USER ?? "admin";
  const next = process.env.SPNC_E2E_ADMIN_NEW_PASSWORD!;
  const r = await login(api, user, next);
  if (r.status() === 200) return (await r.json()).access_token as string;
  return readyUser(api, user, process.env.SPNC_E2E_ADMIN_PASSWORD!, next);
}

/** Creates a user with the temporary password; `ready` also completes the forced change via the API. */
export async function createUser(admin: string, role: "STUDENT" | "TEACHER", ready: boolean): Promise<Person> {
  const api = await ctx();
  const username = `pw_${role.toLowerCase()}_${randomUUID().slice(0, 8)}`;
  const r = await api.post(`${API}/admin/users`, {
    data: { username, email: `${username}@spnc.io`, password: TEMP_PW, full_name: username, role },
    headers: bearer(admin),
  });
  expect([200, 201], await r.text()).toContain(r.status());
  const id = (await r.json()).id as string;
  const token = ready ? await readyUser(api, username, TEMP_PW, FINAL_PW) : "";
  return { id, username, token };
}

/** A PUBLIC Python problem with one sample and one hidden case; the student joins the teacher's class. */
export async function setupProblem(teacher: Person, student: Person): Promise<{ problemId: string; classId: string }> {
  const api = await ctx();
  const h = bearer(teacher.token);
  const p = await api.post(`${API}/problems`, {
    data: { title: `PW Sum ${randomUUID().slice(0, 4)}`, description: "Tính a + b", visibility: "PUBLIC", supported_languages: ["PYTHON3"] },
    headers: h,
  });
  expect(p.status(), await p.text()).toBeLessThan(300);
  const problemId = (await p.json()).id as string;
  for (const [input_data, expected_output, is_sample] of [
    ["1 2\n", "3\n", true],
    ["40 2\n", "42\n", false],
  ] as const) {
    const tc = await api.post(`${API}/problems/${problemId}/test-cases`, { data: { input_data, expected_output, is_sample }, headers: h });
    expect(tc.status(), await tc.text()).toBe(201);
  }
  const c = await api.post(`${API}/classes`, { data: { name: "PW", academic_year: "2026" }, headers: h });
  const cls = await c.json();
  const j = await api.post(`${API}/my/classes/join`, { data: { invite_code: cls.invite_code }, headers: bearer(student.token) });
  expect(j.status(), await j.text()).toBe(201);
  return { problemId, classId: cls.id as string };
}

export async function latestSessionId(student: Person, problemId: string): Promise<string> {
  const api = await ctx();
  const r = await api.get(`${API}/my/practice/sessions?page=1&size=100`, { headers: bearer(student.token) });
  const s = (await r.json()).items.find((x: { problem_id: string }) => x.problem_id === problemId);
  expect(s).toBeTruthy();
  return s.id as string;
}

export interface ServerEvent {
  sequence_number: number;
  event_type: string;
  payload: Record<string, unknown>;
}

/** The trace as the teacher replay API returns it (sequence order). */
export async function serverTrace(teacher: Person, classId: string, studentId: string, sessionId: string): Promise<ServerEvent[]> {
  const api = await ctx();
  const r = await api.get(`${API}/classes/${classId}/students/${studentId}/sessions/${sessionId}/trace-events?skip=0&limit=1000`, {
    headers: bearer(teacher.token),
  });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()).items as ServerEvent[];
}

/** Full source code of a snapshot, as the teacher observation API serves it. */
export async function snapshotSource(teacher: Person, classId: string, studentId: string, sessionId: string, snapshotId: string): Promise<string> {
  const api = await ctx();
  const r = await api.get(`${API}/classes/${classId}/students/${studentId}/sessions/${sessionId}/snapshots/${snapshotId}`, {
    headers: bearer(teacher.token),
  });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()).source_code as string;
}

export function expectContiguous(events: ServerEvent[]) {
  const seqs = events.map((e) => e.sequence_number);
  expect(seqs).toEqual(Array.from({ length: seqs.length }, (_, i) => i + 1));
}

export async function uiLogin(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Tên đăng nhập").fill(username);
  await page.getByLabel("Mật khẩu").fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
}

export async function typeInEditor(page: Page, text: string) {
  await page.locator(".monaco-editor .view-lines").click();
  await page.keyboard.type(text, { delay: 15 });
}

/** Editor text as rendered (Monaco renders spaces as no-break spaces). */
export async function editorText(page: Page): Promise<string> {
  const lines = await page.locator(".monaco-editor .view-line").allInnerTexts();
  return lines.map((l) => l.replace(new RegExp(String.fromCharCode(160), "g"), " ")).join("\n");
}

export async function waitTraceFlushed(page: Page) {
  const badge = page.getByTestId("trace-status");
  await expect(badge).toHaveAttribute("data-pending", "0");
  await expect(badge).toHaveAttribute("data-phase", "idle");
}
