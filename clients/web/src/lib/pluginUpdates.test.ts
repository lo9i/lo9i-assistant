import { describe, expect, it } from "vitest";
import { ApiError, DaemonUnavailableError } from "./api/errors";
import type { FoundServer } from "./api/types";
import { keyOf, pluginsOf } from "./plugins";
import { type CheckState, type UpdateStep, checkRepositories, needsValues, updateEach } from "./pluginUpdates";

const server = (name: string): FoundServer => ({
  name,
  description: "",
  transport: "stdio",
  fields: [],
  trusted: false,
  skill: false,
  page: false,
  channel: false,
  installed: true,
  version: "2",
  installed_version: "1",
  category: "other/general",
  model_login: "",
  ssh_agent: false,
  login_session: false,
  oauth: "",
  subagent: "",
  check: false,
  agent: "",
  email: false,
});
const plugins = pluginsOf({ skills: [], servers: [server("watchlist"), server("expenses"), server("notes")] });

describe("updateEach", () => {
  it("shows every row waiting, then updates them one at a time, going on past a failure", async () => {
    const steps: [string, UpdateStep][] = [];
    const errors: unknown[] = [];
    let running = 0;
    const got = await updateEach(
      plugins,
      async (p) => {
        running += 1;
        expect(running).toBe(1);
        await Promise.resolve();
        running -= 1;
        if (p.name === "expenses") throw new Error("no network");
      },
      (key, step) => steps.push([key.split(":")[1], step]),
      (e) => errors.push(e),
    );
    expect(steps).toEqual([
      ["watchlist", "waiting"],
      ["expenses", "waiting"],
      ["notes", "waiting"],
      ["watchlist", "updating"],
      ["watchlist", "updated"],
      ["expenses", "updating"],
      ["expenses", "failed"],
      ["notes", "updating"],
      ["notes", "updated"],
    ]);
    expect(got).toEqual({ updated: ["watchlist", "notes"], failed: ["expenses"], asking: [] });
    expect(errors).toEqual([new Error("no network")]);
  });

  it("leaves one whose new version asks for a value to ask for, not as a failure", async () => {
    const steps: [string, UpdateStep][] = [];
    const errors: unknown[] = [];
    const got = await updateEach(
      plugins,
      async (p) => {
        if (p.name === "expenses") throw new ApiError(409, "The new version of expenses needs Your bank.");
      },
      (key, step) => steps.push([key.split(":")[1], step]),
      (e) => errors.push(e),
    );
    expect(steps.filter(([name]) => name === "expenses")).toEqual([
      ["expenses", "waiting"],
      ["expenses", "updating"],
      ["expenses", "values"],
    ]);
    expect(got.updated).toEqual(["watchlist", "notes"]);
    expect(got.failed).toEqual([]);
    expect(got.asking).toEqual([{ name: "expenses", key: keyOf(plugins[1]), reason: "The new version of expenses needs Your bank." }]);
    expect(errors).toEqual([]);
  });
});

describe("checkRepositories", () => {
  async function states(read: () => Promise<unknown>): Promise<CheckState[]> {
    const seen: CheckState[] = [];
    await checkRepositories(read, (s) => seen.push(s));
    return seen;
  }

  it("is checking while the repositories are read, then idle", async () => {
    expect(await states(async () => [])).toEqual(["checking", "idle"]);
  });

  it("fails quietly when they can't be read", async () => {
    expect(await states(() => Promise.reject(new Error("no network")))).toEqual(["checking", "failed"]);
  });

  it("leaves an unreachable daemon to the app's banner", async () => {
    expect(await states(() => Promise.reject(new DaemonUnavailableError("down")))).toEqual(["checking", "idle"]);
  });
});

describe("needsValues", () => {
  it("is an update refused only for a value not given yet", () => {
    expect(needsValues(new ApiError(409, "The new version of hello needs Your city."))).toBe(true);
    expect(needsValues(new ApiError(400, "The repository doesn't have hello any more."))).toBe(false);
    expect(needsValues(new DaemonUnavailableError())).toBe(false);
  });
});
