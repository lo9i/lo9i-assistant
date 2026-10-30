import { describe, expect, it } from "vitest";
import { DaemonUnavailableError } from "./api/errors";
import type { FoundServer } from "./api/types";
import { pluginsOf } from "./plugins";
import { type CheckState, type UpdateStep, checkRepositories, updateEach } from "./pluginUpdates";

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
  oauth: "",
  subagent: "",
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
    expect(got).toEqual({ updated: ["watchlist", "notes"], failed: ["expenses"] });
    expect(errors).toEqual([new Error("no network")]);
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
