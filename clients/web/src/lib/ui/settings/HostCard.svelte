<script lang="ts">
  import { Download, LoaderCircle, Power, RefreshCw, RotateCcw, SearchCheck } from "@lucide/svelte";
  import type { HostStatus, UpdateStatus } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { CONFIRM, endingText, waitingText, type Ending } from "$lib/shutdown";
  import { canInstall, updateLine, versionText } from "$lib/updates";
  import Confirm from "../Confirm.svelte";
  import Modal from "../Modal.svelte";
  import SettingsCard from "../Card.svelte";

  const { client, hub, notices } = useDaemon();
  // Read when the page opens and when the user refreshes: use changes all the time, so no event announces it.
  const loaded = resource((c) => c.system.host(), []);
  const h = $derived(loaded.data);
  // Each change of an update's state comes as an `update` event.
  const update = resource((c) => c.system.updateStatus(), ["update"]);
  let confirming = $state<Ending | "update" | null>(null);
  let checking = $state(false);
  // Set once the daemon accepted a restart or stop, from this page or anywhere (an update installed, another
  // tab, before this page loaded); the page waits for it to come back. While it waits for runs to end, it can be
  // taken back, or made to go ahead now by cancelling them.
  let ending = $state<{ ending: Ending; waiting: number } | null>(null);
  // Cancel or Now was pressed and the daemon hasn't answered yet.
  let answering = $state(false);

  $effect(() => {
    void pending();
    return hub.on(["ending"], (data) => {
      ending = data.taken_back ? null : { ending: data.ending as Ending, waiting: Number(data.waiting_for_runs ?? 0) };
    });
  });
  // How many runs it still waits for; once none, it's going ahead and the count stays.
  $effect(() => hub.on(["run_finished"], () => void pending()));

  async function pending(): Promise<void> {
    try {
      const found = await client.system.ending();
      if (found.ending) ending = { ending: found.ending as Ending, waiting: found.waiting_for_runs };
    } catch (e) {
      notices.report(e);
    }
  }

  async function takeBack(): Promise<void> {
    await whileAnswering(async () => {
      await client.system.takeBackEnding();
      ending = null;
    });
  }

  async function now(): Promise<void> {
    await whileAnswering(() => client.system.endNow());
  }

  async function whileAnswering(action: () => Promise<unknown>): Promise<void> {
    answering = true;
    try {
      await action();
    } catch (e) {
      notices.report(e);
    } finally {
      answering = false;
    }
  }

  // The events stream reconnects on its own; once it does, the daemon is back, maybe with a new web build.
  $effect(() => {
    if (ending) return hub.onReconnect(() => location.reload());
  });

  async function end(kind: Ending): Promise<void> {
    try {
      const status = await (kind === "restart" ? client.system.restart() : client.system.stop());
      ending = { ending: kind, waiting: status.waiting_for_runs };
    } catch (e) {
      notices.report(e);
    }
  }

  async function check(): Promise<void> {
    checking = true;
    try {
      await client.system.checkForUpdate();
      await update.reload();
    } catch (e) {
      notices.report(e);
    } finally {
      checking = false;
    }
  }

  async function install(): Promise<void> {
    try {
      await client.system.update();
    } catch (e) {
      notices.report(e);
    }
  }

  function busy(status: UpdateStatus): boolean {
    return checking || ["checking", "updating", "restarting"].includes(status.state);
  }

  function size(bytes: number): string {
    return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  }

  function usage(used: number, total: number): string {
    return `${size(used)} / ${size(total)} (${((used / total) * 100).toFixed(1)}%)`;
  }

  function uptime(seconds: number): string {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return days ? `${days}d ${hours}h ${minutes}m` : `${hours}h ${minutes}m`;
  }

  function rows(h: HostStatus): Array<[string, string]> {
    const rows: Array<[string, string]> = [
      ["OS", h.os],
      ["Arch", h.arch],
      ["Host", h.hostname],
      ["Python", h.python],
      ["lo9i", update.data ? `v${h.version} · ${versionText(update.data.current)}` : `v${h.version}`],
      ["CPU", `${h.cpu_cores} cores · ${Math.round(h.cpu_percent)}%`],
      ["Memory", usage(h.memory_used, h.memory_total)],
      ["Disk", usage(h.disk_used, h.disk_total)],
      ["Uptime", uptime(h.uptime_seconds)],
    ];
    if (h.load_average.length) rows.push(["Load avg", h.load_average.map((l) => l.toFixed(2)).join(" / ")]);
    return rows;
  }
</script>

<SettingsCard id="host" title="Host" sub="The computer the assistant runs on.">
  {#snippet status()}
    <button class="btn btn--sm" onclick={loaded.reload}><RefreshCw size={14} /> Refresh</button>
  {/snippet}
  {#if h === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else}
    <dl>
      {#each rows(h) as [term, value] (term)}
        <div>
          <dt class="micro-label">{term}</dt>
          <dd>{value}</dd>
        </div>
      {/each}
    </dl>
    {#if update.data}
      {@const u = update.data}
      <section class="update">
        <p class="micro-label">Updates</p>
        <p class="text-label" class:error-text={u.state === "failed"}>
          {#if busy(u)}<LoaderCircle size={14} class="spin" aria-hidden="true" />{/if}
          {updateLine(u)}
        </p>
        {#if u.new.length && u.state !== "restarting"}
          <ul class="commits">
            {#each u.new as commit (commit.sha)}
              <li><code>{commit.sha.slice(0, 7)}</code> {commit.subject}</li>
            {/each}
          </ul>
        {/if}
      </section>
    {/if}
    <div class="actions">
      {#if update.data?.installed_from === "git"}
        <button class="btn btn--sm" onclick={check} disabled={busy(update.data)}>
          <SearchCheck size={14} /> Check for updates
        </button>
      {/if}
      {#if update.data && canInstall(update.data)}
        <button class="btn btn--sm btn--primary" onclick={() => (confirming = "update")} disabled={busy(update.data)}>
          <Download size={14} /> Update and restart
        </button>
      {/if}
      <button class="btn btn--sm" onclick={() => (confirming = "restart")}><RotateCcw size={14} /> Restart</button>
      <button class="btn btn--sm btn--danger" onclick={() => (confirming = "stop")}><Power size={14} /> Stop</button>
    </div>
  {/if}
</SettingsCard>

{#if confirming === "update"}
  <Confirm
    title="Update the assistant?"
    text="It downloads the new version, installs what it needs and restarts once the runs in progress end. This page reloads when it's back."
    action="Update"
    onanswer={(yes) => {
      confirming = null;
      if (yes) void install();
    }}
  />
{:else if confirming}
  {@const kind = confirming}
  <Confirm
    {...CONFIRM[kind]}
    onanswer={(yes) => {
      confirming = null;
      if (yes) void end(kind);
    }}
  />
{/if}

{#if ending}
  <!-- No way to close it: the page has nothing to show until the daemon is back, and then it reloads. While it
       waits for runs, Cancel takes it back and Now cancels them. -->
  <Modal title={ending.ending === "restart" ? "Restarting" : "Stopping"} width={440}>
    <p class="text-label">{endingText(ending.ending, ending.waiting)}</p>
    {#if ending.waiting}
      <p class="text-meta">{waitingText(ending.ending)}</p>
    {/if}
    <p class="text-meta waiting"><LoaderCircle size={14} class="spin" aria-hidden="true" /> Waiting for the assistant…</p>
    {#snippet footer()}
      {#if ending?.waiting}
        <button class="btn btn--ghost" onclick={takeBack} disabled={answering}>Cancel</button>
        <button class="btn btn--danger" onclick={now} disabled={answering}>Now</button>
      {/if}
    {/snippet}
  </Modal>
{/if}

<style>
  dl {
    margin: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 16px 24px;
  }
  dd {
    margin: 4px 0 0;
    overflow-wrap: anywhere;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .update {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .update .text-label {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .update :global(.spin) {
    animation: spin 1s linear infinite;
  }
  .commits {
    margin: 0;
    padding: 0;
    list-style: none;
    max-height: 180px;
    overflow-y: auto;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
  }
  .commits li {
    padding: 2px 0;
  }
  p {
    margin: 0;
  }
  .waiting {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
  }
  .waiting :global(.spin) {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .waiting :global(.spin),
    .update :global(.spin) {
      animation: none;
    }
  }
</style>
