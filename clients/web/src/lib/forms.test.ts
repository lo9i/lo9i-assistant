import { describe, expect, it } from "vitest";
import type { FormField } from "./api/types";
import { formContent, startValue } from "./forms";

const field = (key: string, type: FormField["type"], required = false, extra: Partial<FormField> = {}): FormField => ({
  key,
  title: key.toUpperCase(),
  description: "",
  type,
  required,
  ...extra,
});

describe("forms", () => {
  it("starts from each field's default", () => {
    expect(startValue(field("n", "integer", false, { default: 3 }))).toBe("3");
    expect(startValue(field("b", "boolean"))).toBe(false);
    expect(startValue(field("c", "choices", false, { default: ["a"] }))).toEqual(["a"]);
  });

  it("sends what's filled in as its type and names the required fields left empty", () => {
    const fields = [field("size", "choice", true), field("count", "integer"), field("gift", "boolean"), field("note", "text")];
    expect(formContent(fields, { size: "", count: "2", gift: true, note: "" })).toEqual({
      content: { count: 2, gift: true },
      missing: ["SIZE"],
    });
  });
});
