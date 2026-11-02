<script lang="ts">
  import { RefreshCw } from "@lucide/svelte";
  import type { HostStatus } from "$lib/api/types";
  import { resource } from "$lib/daemon.svelte";
  import { formatNumber, t } from "$lib/i18n.svelte";
  import { versionText } from "$lib/updates";
  import SettingsCard from "../Card.svelte";

  // Read when the page opens and when the user refreshes: use changes all the time, so no event announces it.
  const loaded = resource((c) => c.system.host(), []);
  const h = $derived(loaded.data);
  // The version it runs, as the Assistant card's updates say it; each change comes as an `update` event.
  const update = resource((c) => c.system.updateStatus(), ["update"]);

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
  {/if}
</SettingsCard>

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
  p {
    margin: 0;
  }
</style>
