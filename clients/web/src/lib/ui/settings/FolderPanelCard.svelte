<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import SettingsCard from "../Card.svelte";
  import Toggle from "../Toggle.svelte";

  // The folder panel beside a conversation (the agent's folder, or the home folder) shows files read only until this
  // is on; on, a file shown there can be deleted, after a confirmation. Kept by the daemon, so it holds for every
  // device, and off until the user turns it on.
  const { client, notices } = useDaemon();
  const deleting = resource((c) => c.folders.deleting(), ["settings"]);

  async function change(enabled: boolean): Promise<void> {
    try {
      await client.folders.setDeleting(enabled);
    } catch (e) {
      notices.report(e);
    }
    deleting.reload();
  }
</script>

<SettingsCard id="folder-panel" title={t("folderPanelCard.title")} sub={t("folderPanelCard.sub")}>
  {#if deleting.data !== undefined}
    <div class="switch">
      <span class="text-label">{t("folderPanelCard.delete")}</span>
      <Toggle checked={deleting.data} label={t("folderPanelCard.deleteLabel")} onchange={change} />
    </div>
  {/if}
</SettingsCard>

<style>
  .switch {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
</style>
