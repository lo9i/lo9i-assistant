import { describe, expect, it } from "vitest";
import { savedAnswers, startAnswers } from "./aboutYou.svelte";

describe("the About you step's answers", () => {
  it("start empty without a profile, and from what it holds otherwise", () => {
    expect(startAnswers(null)).toEqual({ name: "", language: "", reply_length: null, help_with: [], other_help: "", email: "" });
    const answers = {
      name: "Ana",
      language: "Spanish",
      reply_length: "short" as const,
      help_with: ["coding" as const],
      other_help: "",
      email: "ana@home.org",
    };
    expect(startAnswers({ answers, needed: false })).toEqual(answers);
  });

  it("are saved trimmed, with the topics in the order shown", () => {
    const form = {
      name: "  Ana ",
      language: " Spanish",
      reply_length: null,
      help_with: ["hosts" as const, "email" as const],
      other_help: " trips ",
      email: " ana@home.org ",
    };
    expect(savedAnswers(form)).toEqual({
      name: "Ana",
      language: "Spanish",
      reply_length: null,
      help_with: ["email", "hosts"],
      other_help: "trips",
      email: "ana@home.org",
    });
  });
});
