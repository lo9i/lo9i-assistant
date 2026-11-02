<script lang="ts">
  import { Download, LoaderCircle, RefreshCw, SearchCheck } from "@lucide/svelte";
  import type { HostStatus, UpdateStatus } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { formatNumber, t } from "$lib/i18n.svelte";
  import { canInstall, updateLine, versionText } from "$lib/updates";
  import Confirm from "../Confirm.svelte";
  import SettingsCard from "../Card.svelte";
  import EndingDialog from "./EndingDialog.svelte";

  const { client, notices } = useDaemon();
  // Read when the page opens and when the user refreshes: use changes all the time, so no event announces it.
  const loaded = resource((c) => c.system.host(), []);
  const h = $derived(loaded.data);
  // Each change of an update's state comes as an `update` event.
  const update = resource((c) => c.system.updateStatus(), ["update"]);
  let confirming = $state(false);
  let checking = $state(false);

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
    {#if update.data && (update.data.installed_from === "git" || canInstall(update.data))}
      {@const u = update.data}
      <div class="actions">
        {#if u.installed_from === "git"}
          <button class="btn btn--sm" onclick={check} disabled={busy(u)}>
            <SearchCheck size={14} />
            {t("host.check")}
          </button>
        {/if}
        {#if canInstall(u)}
          <button class="btn btn--sm btn--primary" onclick={() => (confirming = true)} disabled={busy(u)}>
            <Download size={14} />
            {t("host.updateAndRestart")}
          </button>
        {/if}
      </div>
    {/if}
  {/if}
</SettingsCard>

{#if confirming}
  <Confirm
    title={t("host.updateTitle")}
    text={t("host.updateText")}
    action={t("common.update")}
    onanswer={(yes) => {
      confirming = false;
      if (yes) void install();
    }}
  />
{/if}

<!-- An update installed restarts the daemon. -->
<EndingDialog />

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
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .update :global(.spin) {
      animation: none;
    }
  }
</style>
