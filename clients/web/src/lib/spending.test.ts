import { describe, expect, it } from "vitest";
import { fieldsOf, limitsOf } from "./spending";

describe("spending limits as fields", () => {
  it("show each limit as its amount, and none as empty", () => {
    expect(fieldsOf({ job_run: 0.5, job_day: null, conversation: 2, day: null })).toEqual({
      job_run: "0.5",
      job_day: "",
      conversation: "2",
      day: "",
    });
  });

  it("read an empty field as no limit and refuse one that isn't a number", () => {
    expect(limitsOf({ job_run: " 0.5 ", job_day: "", conversation: "2", day: "" })).toEqual({
      job_run: 0.5,
      job_day: null,
      conversation: 2,
      day: null,
    });
    expect(limitsOf({ job_run: "five", job_day: "", conversation: "", day: "" })).toBeNull();
  });
});
