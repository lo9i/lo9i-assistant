<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import Toggle from "../Toggle.svelte";
  import SettingsCard from "../Card.svelte";

  const { client } = useDaemon();
  const checks = resource((c) => c.repositories.updateChecks(), ["settings"]);
  let message = $state("");

  async function change(enabled: boolean): Promise<void> {
    try {
      await client.repositories.setUpdateChecks(enabled);
      message = "";
    } catch (e) {
      message = describe(e);
    }
    checks.reload();
  }
</script>

<SettingsCard id="plugin-updates" title="Plugin updates" sub="Newer versions of installed plugins show as a count on Settings in the sidebar and on the Plugins tab.">
  {#if checks.data === undefined}
    <p class="text-meta">{checks.error ?? "Loading…"}</p>
  {:else}
    <div class="setting">
      <div class="label">
        <span class="text-label">Check once a day</span>
        <span class="text-caption">Off: the extras are checked only when you open Plugins.</span>
      </div>
      <Toggle checked={checks.data.enabled} label="Check for plugin updates" onchange={change} />
    </div>
  {/if}
  {#if message}<p class="text-meta">{message}</p>{/if}
</SettingsCard>

<style>
  .setting {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .label {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  p {
    margin: 0;
  }
</style>
