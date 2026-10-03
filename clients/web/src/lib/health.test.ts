import { describe, expect, it } from "vitest";
import { failingNotice, failures, signedOutNotice } from "./health";

describe("failures", () => {
  it("is empty while it works", () => {
    expect(failures({ failures: 0, failure: "old", failed_at: "2026-10-03T12:00:00+00:00" })).toBe("");
  });

  it("gives the count and the last failure", () => {
    const health = { failures: 3, failure: "exit code: 1", failed_at: "2026-10-03T12:00:00+00:00" };
    expect(failures(health, "UTC")).toBe("Failed 3 times in a row. Last, Sat 03 Oct 12:00: exit code: 1");
    expect(failures({ ...health, failures: 1 }, "UTC")).toBe("Failed once. Last, Sat 03 Oct 12:00: exit code: 1");
  });
});

describe("failingNotice", () => {
  it("names the server or skill and where to look", () => {
    expect(failingNotice({ area: "mcp", name: "notes", error: "disk full" })).toBe(
      "The MCP server notes keeps failing: disk full. It's listed in Alerts.",
    );
    expect(failingNotice({ area: "skill", name: "backup", error: "exit code: 1" })).toBe(
      "The skill backup keeps failing: exit code: 1. It's listed in Alerts.",
    );
  });
});

describe("signedOutNotice", () => {
  it("names the server and where it's listed", () => {
    expect(signedOutNotice({ name: "linear", error: "linear needs you to sign in again." })).toBe(
      "The MCP server linear needs you to sign in again. It's listed in Alerts.",
    );
  });
});
