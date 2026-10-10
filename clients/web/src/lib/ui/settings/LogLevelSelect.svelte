<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
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
  <label
    class="record"
    title="The lowest level the daemon writes to its log, from now on. Debug records more detail, for finding a problem; libraries stay at Info."
  >
    <span class="micro-label">Record</span>
    <select class="input" value={recorded.data.level} onchange={(e) => change(e.currentTarget.value)} aria-label="Level the daemon records">
      {#each levels as level (level)}
        <option value={level}>{levelLabel(level)} and above</option>
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
