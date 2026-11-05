import { describe, expect, it } from "vitest";
import type { Alert, Cause } from "./api/types";
import { changeLabel, contextShare, doctorProblem, partSize, setupSummary, times } from "./doctor";

const cause: Cause = {
  id: "c1",
  kind: "log",
  level: "ERROR",
  title: "ConnectionError: refused",
  where: "lo9i/core/mcp/hub.py in _connect",
  count: 3,
  first: "2026-10-24T09:00:00+00:00",
  last: "2026-10-24T11:00:00+00:00",
  example: "",
  threads: [],
  change: "growing",
  before: 1,
};

describe("causes", () => {
  it("say how they changed and how often they happened", () => {
    expect(changeLabel(cause)).toBe("Growing");
    expect(times(cause)).toBe("3 times (1 the day before)");
    expect(times({ ...cause, change: "new", count: 1 })).toBe("Once");
    expect(changeLabel({ ...cause, change: "" })).toBe("");
  });
});

describe("the starting context", () => {
  it("is a share of the window, each part with its change", () => {
    expect(contextShare({ tokens: 45_000, window: 150_000, parts: [], too_large: true })).toBe("30%");
    expect(partSize({ name: "Saved facts", tokens: 3100, before: 2300 })).toBe("3.1k (+800)");
    expect(partSize({ name: "Skills", tokens: 900, before: 1000 })).toBe("900 (−100)");
    expect(partSize({ name: "Profile", tokens: 400, before: null })).toBe("400");
  });
});

describe("doctorProblem", () => {
  it("names the change, or the context", () => {
    const alert: Alert = { area: "doctor", name: "c1", failures: 3, error: "", at: "", kind: "growing", title: "x" };
    expect(doctorProblem(alert)).toBe("Growing, 3 times");
    expect(doctorProblem({ ...alert, kind: "new", failures: 1 })).toBe("New, once");
    expect(doctorProblem({ ...alert, kind: "context" })).toBe("Starting context large");
  });
});

describe("the setup check", () => {
  it("sums up what fails first, then what warns", () => {
    const check = (status: "ok" | "warn" | "fail") => ({ id: status, title: "x", status, detail: "", fix: "" });
    expect(setupSummary([check("ok"), check("warn"), check("fail")])).toEqual({ label: "1 failing", tone: "danger" });
    expect(setupSummary([check("warn"), check("warn")])).toEqual({ label: "2 warnings", tone: "warn" });
    expect(setupSummary([check("ok")])).toEqual({ label: "All ok", tone: "accent" });
  });
});
