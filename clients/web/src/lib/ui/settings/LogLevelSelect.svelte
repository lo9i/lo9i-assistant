<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { levelLabel } from "$lib/logs";

  // The lowest level the daemon writes to its log, applied at once. Next to the Logs page's controls:
  // its Debug filter finds entries only while this is at Debug.
  let { levels }: { levels: string[] } = $props();

  const { client, notices } = useDaemon();
  const recorded = resource((c) => c.logs.level(), ["settings"]);

  async function change(level: string): Promise<void> {
    try {
      await client.logs.setLevel(level);
    } catch (e) {
      notices.report(e);
    }
    recorded.reload();
  }
</script>

{#if recorded.data !== undefined}
  <label class="record" title={t("logs.recordHint")}>
    <span class="micro-label">{t("logs.record")}</span>
    <select class="input" value={recorded.data.level} onchange={(e) => change(e.currentTarget.value)} aria-label={t("logs.recordLabel")}>
      {#each levels as level (level)}
        <option value={level}>{t("logs.andAbove", { level: levelLabel(level) })}</option>
      {/each}
    </select>
  </label>
{/if}

<style>
  .record {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .record select {
    width: auto;
  }
</style>
