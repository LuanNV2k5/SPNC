import { api, call, type Schemas } from "../../api/client";

export type Problem = Schemas["ProblemResponse"];
export type TestCase = Schemas["TestCaseResponse"];
export type Publication = Schemas["PublicationResponse"];
export type ProblemBody = Schemas["ProblemCreateRequest"];

export interface ProblemFilters {
  page: number;
  difficulty?: "EASY" | "MEDIUM" | "HARD";
  language?: "CPP17" | "PYTHON3";
  visibility?: "PRIVATE" | "CLASS" | "PUBLIC";
}

export const problemKeys = {
  list: (filters: ProblemFilters) => ["t", "problems", filters] as const,
  detail: (id: string) => ["t", "problem", id] as const,
  testCases: (id: string) => ["t", "problem-test-cases", id] as const,
  publications: (id: string) => ["t", "problem-publications", id] as const,
};

export const listProblems = (filters: ProblemFilters) =>
  call(api.GET("/api/v1/problems", { params: { query: { ...filters, size: 20 } } }));
export const getProblem = (problem_id: string) =>
  call(api.GET("/api/v1/problems/{problem_id}", { params: { path: { problem_id } } }));
export const createProblem = (body: ProblemBody) => call(api.POST("/api/v1/problems", { body }));
export const updateProblem = (problem_id: string, body: Schemas["ProblemUpdateRequest"]) =>
  call(api.PATCH("/api/v1/problems/{problem_id}", { params: { path: { problem_id } }, body }));
export const deleteProblem = (problem_id: string) =>
  call(api.DELETE("/api/v1/problems/{problem_id}", { params: { path: { problem_id } } }));

export const listTestCases = (problem_id: string) =>
  call(api.GET("/api/v1/problems/{problem_id}/test-cases", { params: { path: { problem_id } } }));
export const createTestCase = (problem_id: string, body: Schemas["TestCaseCreate"]) =>
  call(api.POST("/api/v1/problems/{problem_id}/test-cases", { params: { path: { problem_id } }, body }));
export const updateTestCase = (problem_id: string, test_case_id: string, body: Schemas["TestCaseUpdate"]) =>
  call(api.PATCH("/api/v1/problems/{problem_id}/test-cases/{test_case_id}", { params: { path: { problem_id, test_case_id } }, body }));
export const deleteTestCase = (problem_id: string, test_case_id: string) =>
  call(api.DELETE("/api/v1/problems/{problem_id}/test-cases/{test_case_id}", { params: { path: { problem_id, test_case_id } } }));

export const listPublications = (problem_id: string) =>
  call(api.GET("/api/v1/problems/{problem_id}/publications", { params: { path: { problem_id } } }));
export const publishProblem = (problem_id: string, class_id: string) =>
  call(api.POST("/api/v1/problems/{problem_id}/publish", { params: { path: { problem_id } }, body: { class_id } }));
export const unpublishProblem = (problem_id: string, class_id: string) =>
  call(api.DELETE("/api/v1/problems/{problem_id}/publish/{class_id}", { params: { path: { problem_id, class_id } } }));
