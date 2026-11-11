// What the System and General tabs' cards read from the daemon, for their tests.

export const host = {
  os: "Linux 7.0.0",
  arch: "x86_64",
  hostname: "board",
  python: "CPython 3.12.9",
  version: "0.1.0",
  cpu_cores: 4,
  cpu_percent: 5,
  memory_used: 1,
  memory_total: 2,
  disk_used: 1,
  disk_total: 2,
  uptime_seconds: 60,
  load_average: [],
  stop_note: "",
  stop_refusal: "",
};

export const update = {
  installed_from: "git",
  current: { sha: "a1b2c3d4e5", subject: "First", date: "2026-10-24T12:00:00Z" },
  upstream: "origin/main",
  behind: 1,
  new: [{ sha: "b2c3d4e5f6", subject: "Show the subagent's steps", date: "2026-10-24T13:00:00Z" }],
  checked_at: "2026-10-24T14:00:00Z",
  can_update: true,
  reason: "",
  state: "idle",
  step: "",
  error: "",
};

/** A client whose system and identity answer with the above, `changes` over the host. */
export function fakeSystem(changes: Partial<typeof host> = {}) {
  return {
    system: { host: () => ({ ...host, ...changes }), updateStatus: () => update },
    identity: { name: () => "lo9i" },
  };
}
