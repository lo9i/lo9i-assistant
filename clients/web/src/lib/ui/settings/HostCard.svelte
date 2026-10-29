<script lang="ts">
  import { Download, LoaderCircle, Power, RefreshCw, RotateCcw, SearchCheck } from "@lucide/svelte";
  import type { HostStatus, UpdateStatus } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { formatNumber, t } from "$lib/i18n.svelte";
  import { answerable, coming, confirmation, endingText, waitingText, type Coming, type Ending } from "$lib/shutdown";
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
  // tab, before this page loaded); the page waits for it to come back. While it waits, it can be taken back (unless
  // an update was installed), or made to go ahead now by cancelling the runs it waits for.
  let ending = $state<Coming | null>(null);
  // Cancel or Now was pressed and the daemon hasn't answered yet.
  let answering = $state(false);

  $effect(() => {
    void pending();
    return hub.on(["ending"], (data) => (ending = coming(data)));
  });
  // How many runs it still waits for; once none, it's going ahead and the count stays.
  $effect(() => hub.on(["run_finished"], () => void pending()));

  async function pending(): Promise<void> {
    try {
      const found = coming(await client.system.ending());
      if (found) ending = found;
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
      ending = { ending: kind, waiting: status.waiting_for_runs, update: false, canTakeBack: true, neededBy: "" };
      // What else it waits for (an update being installed), and whether it can be taken back.
      void pending();
    } catch (e) {
      notices.report(e);
    }
  }

  // Takes the kind as an argument: `{@const kind}` is derived from `confirming`, so read after clearing it, it's
  // null and the restart would become a stop.
  function answer(kind: Ending, yes: boolean): void {
    confirming = null;
    if (yes) void end(kind);
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
    return `${formatNumber(bytes / 1024 ** 3, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`;
  }

  function usage(used: number, total: number): string {
    const percent = formatNumber(used / total, { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
    return `${size(used)} / ${size(total)} (${percent})`;
  }

  function uptime(seconds: number): string {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return days ? t("host.uptimeDays", { days, hours, minutes }) : t("host.uptime", { hours, minutes });
  }

  function rows(h: HostStatus): Array<[string, string]> {
    const rows: Array<[string, string]> = [
      [t("host.os"), h.os],
      [t("host.arch"), h.arch],
      [t("host.host"), h.hostname],
      ["Python", h.python],
      ["lo9i", update.data ? `v${h.version} · ${versionText(update.data.current)}` : `v${h.version}`],
      ["CPU", t("host.cpu", { cores: h.cpu_cores, percent: Math.round(h.cpu_percent) })],
      [t("host.memory"), usage(h.memory_used, h.memory_total)],
      [t("host.disk"), usage(h.disk_used, h.disk_total)],
      [t("host.uptimeLabel"), uptime(h.uptime_seconds)],
    ];
    const load = h.load_average.map((l) => formatNumber(l, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
    if (h.load_average.length) rows.push([t("host.load"), load.join(" / ")]);
    return rows;
  }
</script>

<SettingsCard id="host" title={t("host.title")} sub={t("host.sub")}>
  {#snippet status()}
    <button class="btn btn--sm" onclick={loaded.reload}><RefreshCw size={14} /> {t("common.refresh")}</button>
  {/snippet}
  {#if h === undefined}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
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
        <p class="micro-label">{t("host.updates")}</p>
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
          <SearchCheck size={14} />
          {t("host.check")}
        </button>
      {/if}
      {#if update.data && canInstall(update.data)}
        <button class="btn btn--sm btn--primary" onclick={() => (confirming = "update")} disabled={busy(update.data)}>
          <Download size={14} />
          {t("host.updateAndRestart")}
        </button>
      {/if}
      <button class="btn btn--sm" onclick={() => (confirming = "restart")}><RotateCcw size={14} /> {t("shutdown.restart")}</button>
      <button
        class="btn btn--sm btn--danger"
        onclick={() => (confirming = "stop")}
        disabled={!!h.stop_refusal}
        title={h.stop_refusal || undefined}><Power size={14} /> {t("shutdown.stop")}</button
      >
    </div>
    {#if h.stop_refusal}<p class="text-caption">{h.stop_refusal}</p>{/if}
  {/if}
</SettingsCard>

{#if confirming === "update"}
  <Confirm
    title={t("host.updateTitle")}
    text={t("host.updateText")}
    action={t("common.update")}
    onanswer={(yes) => {
      confirming = null;
      if (yes) void install();
    }}
  />
{:else if confirming}
  {@const kind = confirming}
  <Confirm {...confirmation(kind)} onanswer={(yes) => answer(kind, yes)} />
{/if}

{#if ending}
  <!-- No way to close it: the page has nothing to show until the daemon is back, and then it reloads. While it
       waits for runs, Cancel takes it back and Now cancels them. -->
  <Modal title={ending.ending === "restart" ? t("host.restarting") : t("host.stopping")} width={440}>
    {@const can = answerable(ending)}
    <p class="text-label">{endingText(ending)}</p>
    {#if can.cancel || can.now}
      <p class="text-meta">{waitingText(ending)}</p>
    {/if}
    <p class="text-meta waiting"><LoaderCircle size={14} class="spin" aria-hidden="true" /> {t("host.waiting")}</p>
    {#snippet footer()}
      {#if ending && answerable(ending).cancel}
        <button class="btn btn--ghost" onclick={takeBack} disabled={answering}>{t("common.cancel")}</button>
      {/if}
      {#if ending && answerable(ending).now}
        <button class="btn btn--danger" onclick={now} disabled={answering}>{t("banner.now")}</button>
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
