<script lang="ts">
  import { RefreshCw } from "@lucide/svelte";
  import type { HostStatus } from "$lib/api/types";
  import { resource } from "$lib/daemon.svelte";
  import SettingsCard from "../Card.svelte";

  // Read when the page opens and when the user refreshes: use changes all the time, so no event announces it.
  const loaded = resource((c) => c.system.host(), []);
  const h = $derived(loaded.data);

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
      ["lo9i", `v${h.version}`],
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
</style>
