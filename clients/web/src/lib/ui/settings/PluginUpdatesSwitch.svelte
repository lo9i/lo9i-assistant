<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import Toggle from "../Toggle.svelte";

  // Daily checks of the extras, next to the Plugins page's tabs. They find newer versions of the
  // installed plugins (counted on Settings in the sidebar and on the Plugins tab) and keep the list
  // of plugins the assistant can offer current; off, the extras are read only when Plugins opens.
  const { client, notices } = useDaemon();
  const checks = resource((c) => c.repositories.updateChecks(), ["settings"]);

  async function change(enabled: boolean): Promise<void> {
    try {
      await client.repositories.setUpdateChecks(enabled);
    } catch (e) {
      notices.report(e);
    }
    checks.reload();
  }
</script>

{#if checks.data !== undefined}
  <div class="switch" title={t("pluginUpdates.switchHint")}>
    <span class="text-label">{t("pluginUpdates.daily")}</span>
    <Toggle checked={checks.data.enabled} label={t("pluginUpdates.dailyLabel")} onchange={change} />
  </div>
{/if}

<style>
  .switch {
    display: flex;
    align-items: center;
    gap: 10px;
  }
</style>
