import type { Schemas } from "../../api/client";

export type Difficulty = "" | "EASY" | "MEDIUM" | "HARD";
export type Visibility = "PRIVATE" | "CLASS" | "PUBLIC";
export type Language = "CPP17" | "PYTHON3";

export interface ProblemDraft {
  title: string;
  description: string;
  constraints: string;
  inputFormat: string;
  outputFormat: string;
  difficulty: Difficulty;
  visibility: Visibility;
  timeLimitMs: number;
  memoryLimitMb: number;
  languages: Language[];
}

export const emptyProblemDraft = (): ProblemDraft => ({
  title: "",
  description: "",
  constraints: "",
  inputFormat: "",
  outputFormat: "",
  difficulty: "",
  visibility: "PRIVATE",
  timeLimitMs: 1000,
  memoryLimitMb: 256,
  languages: ["CPP17", "PYTHON3"],
});

export function draftFromProblem(problem: Schemas["ProblemResponse"]): ProblemDraft {
  return {
    title: problem.title,
    description: problem.description,
    constraints: problem.constraints ?? "",
    inputFormat: problem.input_format ?? "",
    outputFormat: problem.output_format ?? "",
    difficulty: (problem.difficulty ?? "") as Difficulty,
    visibility: problem.visibility as Visibility,
    timeLimitMs: problem.time_limit_ms,
    memoryLimitMb: problem.memory_limit_mb,
    languages: problem.supported_languages as Language[],
  };
}

export function validateProblemDraft(draft: ProblemDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.title.trim()) errors.title = "Tên bài không được để trống.";
  if (!draft.description.trim()) errors.description = "Nội dung đề không được để trống.";
  if (draft.timeLimitMs < 1) errors.timeLimitMs = "Giới hạn thời gian phải lớn hơn 0.";
  if (draft.memoryLimitMb < 1) errors.memoryLimitMb = "Giới hạn bộ nhớ phải lớn hơn 0.";
  if (draft.languages.length === 0) errors.languages = "Chọn ít nhất một ngôn ngữ.";
  return errors;
}

export function problemBody(draft: ProblemDraft): Schemas["ProblemCreateRequest"] {
  return {
    title: draft.title.trim(),
    description: draft.description.trim(),
    constraints: draft.constraints.trim() || null,
    input_format: draft.inputFormat.trim() || null,
    output_format: draft.outputFormat.trim() || null,
    difficulty: draft.difficulty || null,
    visibility: draft.visibility,
    time_limit_ms: draft.timeLimitMs,
    memory_limit_mb: draft.memoryLimitMb,
    supported_languages: draft.languages,
  };
}
