import { describe, expect, it } from "vitest";
import { emptyProblemDraft, problemBody, validateProblemDraft } from "./problemDraft";

describe("teacher problem form", () => {
  it("requires the fields needed by the authoring API", () => {
    const draft = emptyProblemDraft();
    draft.languages = [];
    draft.timeLimitMs = 0;
    expect(validateProblemDraft(draft)).toEqual({
      title: "Tên bài không được để trống.",
      description: "Nội dung đề không được để trống.",
      timeLimitMs: "Giới hạn thời gian phải lớn hơn 0.",
      languages: "Chọn ít nhất một ngôn ngữ.",
    });
  });

  it("trims text and sends empty optional fields as null", () => {
    const draft = emptyProblemDraft();
    draft.title = "  Tổng hai số  ";
    draft.description = "  Tính tổng.  ";
    draft.difficulty = "EASY";
    draft.languages = ["PYTHON3"];
    expect(validateProblemDraft(draft)).toEqual({});
    expect(problemBody(draft)).toMatchObject({
      title: "Tổng hai số",
      description: "Tính tổng.",
      constraints: null,
      input_format: null,
      output_format: null,
      difficulty: "EASY",
      supported_languages: ["PYTHON3"],
    });
  });
});
