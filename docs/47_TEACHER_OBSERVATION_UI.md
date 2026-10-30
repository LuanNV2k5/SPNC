# 47 — TEACHER OBSERVATION UI (PHASE 20B) SPECIFICATION

> **Module:** web client (`apps/web`): teacher class view, session timeline and replay, attention signals, annotations, live notifications
> **Status:** APPROVED 2026-10-30 (all §6 recommendations; see PROJECT_PROVENANCE_LOG.md)
> **Date:** 2026-10-30
> **Parent Baseline:** `phase-20a-frontend-foundation-locked` (`d703d8e`, = `main`)
> **Proposed Branch:** `phase20b`
> **Target Lock Tag:** `phase-20b-teacher-observation-locked`
> **Phase split (ROADMAP §2, docs/46):** 20A foundation + student practice (locked) → **20B teacher session timeline and signals (this document)** → 20C exams → 20D admin and statistics

---

## 1. Purpose

20A produces real trace data; nobody can look at it yet. 20B gives the teacher the screens the backend has served since Phase 09 (docs/35):

- **which students need attention** in a class (REQ-OBS-001);
- **a student's sessions** (REQ-OBS-002);
- **the session timeline** with a **code replay** that can be stepped through event by event and checked against the stored snapshots (REQ-OBS-003/004);
- **attention signals** with their evidence, described neutrally, and their status (acknowledge / dismiss / reopen) (REQ-SIGNAL-003/004, docs/35 D1);
- **annotations** — the teacher's own notes (REQ-OBS-005/006);
- **live updates** over the existing teacher WebSocket (NFR-REALTIME-001..003).

The system shows observable facts and evidence; the teacher interprets them (PROJECT_RULES #20–22). Exam observation is 20C, admin and statistics 20D. Go-live gate G1 still applies.

---

## 2. Findings (2026-10-30)

| # | Finding | Evidence | Impact |
|---|---|---|---|
| F1 | Teacher observation REST is complete: `GET /classes/{c}/attention` (students with NEW signals, names, counts by type), `GET /classes/{c}/students/{s}/sessions` (problem title, context, times, status, verdict, signal count, `trace_purged_at`), `GET …/sessions/{id}/timeline` (events page ≤ 1000 + `state`, all signals, snapshot refs, runs), `GET …/snapshots/{id}` (source code), `GET …/runs`, `GET …/students/{s}/signals` (filters status/session/type). All TEACHER-only and class-scoped by the docs/35 §3 visibility rule. | `api/endpoints/observation.py`, `schemas/observation.py` | No backend work needed for the core screens |
| F2 | Signal status: `PATCH /classes/{c}/students/{s}/signals/{id}` `{status: NEW\|ACKNOWLEDGED\|DISMISSED}`, evidence read-only. Annotations: `POST/GET/PATCH/DELETE /annotations` (own only, plain text 1–5000 chars, soft delete, optional `session_id` / `signal_id`, list filters student/session/signal/date). | `api/endpoints/annotation.py`, docs/35 D1, D7, D8 | Direct mapping to UI actions |
| F3 | `GET /classes/{c}/members` returns only `student_id`, `is_active`, `created_at` — **no username or full name**. Names appear only in the attention list (students with NEW signals). Teachers have no user-read endpoint. | `schemas/academic.py` `MemberResponse`; `endpoints/admin.py` (users are ADMIN-only) | A class roster would show UUIDs (D2) |
| F4 | Teacher WebSocket `/api/v1/ws/teacher`: first message `{type:"auth", access_token}` (close 4401 on bad token, 4403 for non-teachers), then `{type:"subscribe", class_id\|exam_id}`. Server pushes identifiers only: `signal.created`, `run.completed`, `session.state`, `submission.judged`. Cross-process via PostgreSQL `LISTEN/NOTIFY`; best effort; clients must resync over REST after reconnect. Served by uvicorn in compose (compose E2E checks it); the 20A NGINX proxies the upgrade (docs/46 §7.3). No `Origin` check. | `api/endpoints/ws.py`, `realtime/hub.py`, docs/35 D4, NFR-REALTIME-001..003 | Live updates are notifications + refetch (D4); `Origin` decision deferred from docs/46 D6 (D5) |
| F5 | No keystroke stream to teachers (NFR-REALTIME-002): while a session is ACTIVE, new trace events become visible only by refetching the timeline. | NFR-REALTIME-002; `realtime/hub.py` `ALLOWED_KEYS` | An open ACTIVE timeline needs a refresh rule (D4) |
| F6 | Replay: `EDITOR_CHANGED` payloads are diffs (`range_offset`, `range_length`, `text`), applied in sequence order from an empty document (docs/46 D9); 20A ships `applyEditorChanges`. Ground truth points: `SESSION_CHECKPOINT`, `RUN_REQUESTED`, `SUBMISSION_CREATED` carry `code_snapshot_id`. The 20A E2E proves replay = snapshot exactly. A session can have a gap (`highest_contiguous_sequence` < last sequence) and, per docs/46 §7.2, a resumed session can start from an empty editor although earlier keystrokes exist. | `src/trace/payloads.ts`, docs/31, docs/46 §7.2 | Replay must stop at a gap and flag divergence from a snapshot (D3) |
| F7 | `FAST_FIRST_CODE` fires when the first `EDITOR_CHANGED` comes ≤ 30 s (`SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS`) after `session.opened_at`; the domain calls the baseline `problem_open_time`. In the 20A UI the statement is readable **before** the session starts, so a student who reads first and then clicks "Bắt đầu làm bài" types within 30 s and the signal fires on nearly every session. | `services/judge/signals.py:173-210`; `docs/01_DOMAIN.md` l.278; `features/practice/ProblemPage.tsx` | The signal would be noise for teachers unless the problem is "opened" when the statement is shown (D7) |
| F8 | Signal evidence per type (canonical fields, docs/01 §1.8): IDLE `{start_time, end_time, duration_seconds, threshold_used, meaningful_event_before_id}`; FAST_FIRST_CODE `{problem_open_time, first_code_event_time, delta_seconds, threshold_seconds}`; REPEATED_FAILURE `{run_count, failed_count, verdicts[], time_range_start, time_range_end}` (+ `run_ids`, `snapshot_ids`); LOC_ANOMALY `{observed_loc, context_median_loc, delta, threshold_relative, final_loc}`. Legacy duplicate fields are also present. | `services/judge/signals.py` | The UI renders canonical fields and links ids/times to timeline points (D6) |
| F9 | Wording: no judgmental words ("gian lận", "không hiểu", "yếu", "có vấn đề", "đáng ngờ") anywhere in signal labels or evidence display. | REQ-SIGNAL-004, PROJECT_RULES #20–21, docs/01 l.282 | Enforced by a test over the strings file (D6) |
| F10 | Students cannot join a class from the UI (20A has no screen), yet practising PUBLIC problems requires class membership (`PROBLEM_FORBIDDEN` "Join a class…"). Teachers can create classes and see/rotate the invite code: `POST/GET/PATCH /classes`, `POST /classes/{c}/invite-code/rotate`; students: `GET /my/classes`, `POST /my/classes/join`. | `endpoints/academic.py:58-236`, `services/academic.py:455` | A demo still needs Swagger for enrolment unless 20B adds it (D1) |
| F11 | Problem authoring (problems, test cases, publish to class) has endpoints but no UI; neither has exam management (20C). | `endpoints/academic.py`, `endpoints/testcase.py` | Scope choice (D1) |

---

## 3. Scope

### 3.1 Navigation (TEACHER)
`/teacher` → **Lớp của tôi** (own classes, create class) → `/teacher/classes/:classId` (tabs: **Cần chú ý** = attention list with live counts; **Học sinh** = roster with names (D2); invite code with copy and rotate) → `/teacher/classes/:classId/students/:studentId` (sessions table, signals of the student with filters, the teacher's annotations about the student) → `/teacher/classes/:classId/students/:studentId/sessions/:sessionId` (session page, §3.2). The role home for TEACHER becomes `/teacher`. ADMIN keeps the placeholder (20D).

### 3.2 Session page
- **Header:** problem, context, status, opened / first code / ended, working time, final LOC, latest verdict; `trace_purged_at` shown as "Dữ liệu dấu vết chi tiết đã được xoá theo chính sách lưu trữ" (docs/45 §3.6).
- **Replay (D3):** code view (read-only Monaco), a slider and step buttons over the sequence; the event list (sequence, server time, type, short neutral description) is synchronised with the slider; markers for snapshots, runs, submissions and signals. Selecting a snapshot shows its stored content and a diff against the replayed code at that point.
- **Signals:** cards with neutral label, time, canonical evidence fields, a link that moves the replay to the evidence point, and status buttons (ghi nhận / bỏ qua / mở lại).
- **Runs and submissions:** list with verdicts; clicking moves the replay to the run's event.
- **Annotations:** list, add, edit, delete own notes for this session (optionally attached to a signal).
- **Live (D4):** while the session is ACTIVE, the page refreshes on notifications for it and every 15 s.

### 3.3 Replay engine (`src/trace/replay.ts`, pure TS, D3)
1. Load all events: first page from the timeline call, the rest from `GET …/trace-events?skip&limit=1000`, in sequence order.
2. Stop at the first gap (`sequence_number ≠ previous + 1` or beyond `highest_contiguous_sequence`); the UI shows where and why.
3. `codeAt(seq)` applies `EDITOR_CHANGED` diffs from an empty document; results are memoised every 500 events so seeking is fast for 20 000-event sessions (NFR-PERF-008).
4. **Verification:** for each event carrying `code_snapshot_id`, the replayed code at that sequence is compared with the snapshot content (fetched lazily). Equal → ✓; different → "khác với bản lưu" and, from that point on, the replay is **rebased** on the snapshot content (later diffs apply on top), so one missed keystroke does not corrupt the rest.

### 3.4 Live notifications (`src/api/teacherSocket.ts`, D4)
One WebSocket per tab while a teacher page is open: auth message with the current access token, subscribe to the class being viewed (re-subscribe on navigation). Close 4401 → refresh the access token (docs/46 §3.3) → reconnect; other closes → reconnect with backoff 1–30 s. After every (re)connect, the open queries are invalidated (REST resync, NFR-REALTIME-003). A notification invalidates exactly the queries it concerns (attention list, the student's sessions/signals, the session timeline). Status shown as a small badge ("trực tiếp" / "đang kết nối lại").

### 3.5 Class management and enrolment (D1)
- Teacher: create class (name, academic year), see and copy the invite code, rotate it, view the roster.
- Student: **Lớp của tôi** page with joined classes and a "Tham gia lớp" form (invite code). Error codes mapped to Vietnamese.
- Problem authoring stays out of scope (D1).

### 3.6 Practice page change (D7)
The problem page shows title, difficulty, limits and the start button; the **statement, samples and editor appear only after the session starts** (or resumes). A resumed session shows them at once. This makes `session.opened_at` the moment the student first sees the statement, as the domain's `problem_open_time` intends.

### 3.7 Backend change (D2)
Additive, read-only, no migration: `MemberResponse` gains `username` and `full_name` (from the joined `users` row) for the owner teacher's `GET /classes/{c}/members`. OpenAPI and the generated client are regenerated. Covered by a backend test in the `academic` group.

### 3.8 Wording (D6)
All signal labels, evidence captions and event descriptions live in `src/i18n/vi.ts`. Labels describe the observation:
- IDLE_DETECTED — "Không có thao tác trong {n} phút"
- FAST_FIRST_CODE — "Bắt đầu gõ code {n} giây sau khi mở đề"
- REPEATED_FAILURE — "Chạy thử chưa đạt {n} lần liên tiếp, code thay đổi ít"
- LOC_ANOMALY — "Số dòng code {n} so với trung vị {m} của bài"
A Vitest test fails if any string in `vi.ts` contains a forbidden word (F9).

### 3.9 Tests and CI
- **Vitest:** replay engine (diff application, memoised seek = full replay, gap stop, snapshot verification, rebase after mismatch, 20 000-event performance budget < 1 s); teacher socket (auth, subscribe, 4401 → refresh → reconnect, backoff, resync callback) with a fake WebSocket; signal label formatting; forbidden-word test.
- **Backend:** `MemberResponse` names test (group `academic`).
- **Playwright** (compose stack, existing step in `compose-e2e`): (1) teacher creates a class, student joins with the code in the UI, the roster shows the student's name; (2) student practises and submits; the teacher opens the session, the replay at the submission point equals the submitted snapshot (✓ on every snapshot), and the FAST_FIRST_CODE signal (student types within 30 s of the statement appearing) can be acknowledged and an annotation added; (3) live: with the teacher's class page open, a student run produces a `run.completed` that updates the page without reload.
- No CI structure change (the `web` job and the Playwright step already exist).

### 3.10 Out of scope
Problem and test-case authoring UI; exam screens and exam observation (20C); statistics, admin screens, ADMIN observation (20D); exporting timelines; real-time keystroke streaming (forbidden, NFR-REALTIME-002); changes to signal rules or thresholds; WebSocket `Origin` allow-list (D5).

---

## 4. Invariants
1. Teachers see only what the backend authorises; no client-side filtering is relied on for privacy (PROJECT_RULES #9).
2. No UI text is judgmental (REQ-SIGNAL-004); signal evidence is displayed, never edited.
3. The WebSocket carries identifiers only; all data comes from REST (NFR-REALTIME-001..003).
4. The replay never invents code: past a gap it stops; past a mismatch it shows the snapshot and says so.
5. Students gain no access to trace, signals or annotations (REQ-STU-003).
6. The only backend change is the additive `MemberResponse` fields (§3.7).
7. All 20A invariants (docs/46 §4) keep holding.

---

## 5. Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-20B-01 | A TEACHER lands on `/teacher`, sees own classes, can create one and copy/rotate its invite code. |
| AC-20B-02 | A STUDENT joins a class with the code from the UI; wrong code shows the mapped error with request id. |
| AC-20B-03 | The roster shows each member's full name and username. |
| AC-20B-04 | The attention tab lists students with NEW signals and counts by type; acknowledging the last NEW signal of a student removes them from it. |
| AC-20B-05 | The student page lists sessions (REQ-OBS-002 fields) and signals with status/type filters. |
| AC-20B-06 | Session replay: stepping to any snapshot point shows code equal to the snapshot (✓); a gap stops the replay with a message; a mismatch is flagged and the replay continues from the snapshot. |
| AC-20B-07 | Signals show neutral labels and canonical evidence; evidence links move the replay; status changes ACK/DISMISS/reopen persist. |
| AC-20B-08 | Annotations: create, edit, delete own notes on a session or signal; others' notes are never shown. |
| AC-20B-09 | Live: a `run.completed` / `signal.created` / `submission.judged` for the class updates the visible data without reload; after a dropped connection the page resyncs. |
| AC-20B-10 | Practice page: statement and editor appear only after the session starts; `FAST_FIRST_CODE` evidence `problem_open_time` equals the moment the statement appeared. |
| AC-20B-11 | Forbidden-word test green; replay of a 20 000-event session seeks in < 1 s in Vitest. |
| AC-20B-12 | Vitest, lint, typecheck, build, client staleness, backend regression and Playwright green locally and in CI. |

---

## 6. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | Scope of 20B | (a) observation screens (§3.1–3.4) **plus** minimal class management for teachers (create class, invite code) and "join class" for students (§3.5); problem authoring deferred to its own small phase after 20B; (b) (a) plus problem and test-case authoring; (c) observation screens only | **(a)**. Without enrolment in the UI no demo works end to end (F10), and it is small. Problem authoring (forms, test cases, publish) is about as large as the observation work itself and is independent of it; keeping it separate keeps 20B reviewable. |
| **D2** | Student names in the roster | (a) additive backend change: `MemberResponse` + `username`, `full_name` (owner teacher only, no migration, §3.7); (b) no backend change: show names only where the API has them (attention list), UUIDs elsewhere | **(a)**. A roster of UUIDs is unusable. The change is read-only, scoped by the existing owner check, and the teacher already sees these names in the attention list. Breaks 20A's "no backend change" only for this phase, with its own test. |
| **D3** | How the timeline shows code | (a) client replay engine (§3.3): all events, diffs from empty, memoised seek, stop at gaps, verify against every snapshot and rebase on mismatch; (b) snapshots only (no keystroke replay); (c) a new server-side replay endpoint | **(a)**. Keystroke replay is the point of the trace; the data and the diff function exist and are proven equal to snapshots (docs/46 §7.3). Verification makes any divergence visible instead of silent. (c) moves the same logic to the backend for no gain. |
| **D4** | Live updates | (a) teacher WebSocket per tab, subscribe to the viewed class, notifications invalidate the affected queries, reconnect with token refresh and backoff, REST resync after reconnect; plus 15 s refresh of an open ACTIVE session's timeline; (b) polling only (e.g. 15 s everywhere); (c) WebSocket only | **(a)**. Uses the backend's designed channel (docs/35 D4) for signals, runs and submissions; the 15 s refresh covers keystrokes, which by design never travel over the socket (F5). |
| **D5** | WebSocket `Origin` check (deferred from docs/46 D6) | (a) no check: auth is a bearer token sent in the first message, no cookies, so a foreign page cannot open an authenticated socket; document it; (b) add an `Origin` allow-list setting in the API (backend change) | **(a)**. Cross-site WebSocket hijacking needs ambient credentials, which this API never uses. An allow-list adds configuration to every deployment for no protection gained; revisit if cookie auth is ever introduced. |
| **D6** | Signal presentation and wording | (a) neutral Vietnamese labels per type (§3.8), canonical evidence as a small table with links to the timeline, raw JSON behind "Chi tiết"; forbidden-word test over `vi.ts`; (b) raw evidence JSON only | **(a)**. Teachers need evidence they can read and check; the test makes REQ-SIGNAL-004 enforceable for every future string. |
| **D7** | `FAST_FIRST_CODE` baseline vs the 20A page (F7) | (a) frontend: statement and editor only after the session starts (§3.6), so `opened_at` = statement first shown; (b) keep the 20A page and accept that the signal fires for students who read before starting; (c) backend: change the rule or its baseline | **(a)**. Restores the meaning the domain gives `problem_open_time` without touching signal rules (out of scope, rule_version). Reading time then counts inside the session, as it should for idle/working time too. (b) floods the attention list with noise from day one. |
| **D8** | Annotations placement | (a) on the session page (session-level or attached to a signal) and listed on the student page; (b) also a class-wide notes page | **(a)**. Covers REQ-OBS-005 where the teacher is looking; a notes overview can come with 20D statistics. |
| **D9** | Tests | (a) §3.9: Vitest for replay, socket, wording; one backend test; 3 Playwright tests in the existing `compose-e2e` step; (b) (a) without live-notification E2E | **(a)**. The live path crosses API, PostgreSQL `NOTIFY`, NGINX and the browser; only an E2E test proves it end to end. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md` before any code is written.

---

## 7. Verification Record

### 7.1 Changes
| Commit | Content |
|---|---|
| `9dacacc` | This specification (draft) |

### 7.2 Implementation Notes (within the approved decisions)
_None yet._

### 7.3 Verification
| Check | Environment | Result |
|---|---|---|
| | | |
