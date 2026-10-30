import { api, call } from "../../api/client";

export const listExams = () => call(api.GET("/api/v1/my/exams", { params: { query: { page: 1, size: 100 } } }));
export const getParticipation = (exam_id: string) =>
  call(api.GET("/api/v1/my/exams/{exam_id}/participation", { params: { path: { exam_id } } }));
export const startParticipation = (exam_id: string) =>
  call(api.POST("/api/v1/my/exams/{exam_id}/start", { params: { path: { exam_id } } }));
export const listExamProblems = (exam_id: string) =>
  call(api.GET("/api/v1/my/exams/{exam_id}/problems", { params: { path: { exam_id } } }));
export const startExamSession = (participation_id: string, problem_id: string, language: string) =>
  call(api.POST("/api/v1/my/exam-sessions", {
    params: { query: { participation_id } },
    body: { problem_id, language },
  }));
export const finalizeExam = (exam_id: string) =>
  call(api.POST("/api/v1/my/exams/{exam_id}/finalize", { params: { path: { exam_id } } }));
