<script lang="ts">
  import SlidersHorizontal from "@lucide/svelte/icons/sliders-horizontal";
  import type { FoundServer } from "$lib/api/types";
  import { resource } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { pluginLabel } from "$lib/plugins";
  import Modal from "../Modal.svelte";
  import PluginSettingsDialog from "../plugins/PluginSettingsDialog.svelte";
  import PluginSetup from "../plugins/PluginSetup.svelte";

  // An installed plugin's setup in the conversation; the run goes on once the user says it's Done. Esc, the scrim and ×
  // only hide it (`onhide`, `hidden`), the run still waiting, unless nothing waits for it (`ondone` then). Opened later
  // (open_plugin_setup, `settings`), it offers the plugin's settings too, which take its place while open; right
  // after it's installed they were just typed.
  type Props = { server: FoundServer; settings?: boolean; ondone: () => void; onhide?: () => void; hidden?: boolean };
  let { server, settings = false, ondone, onhide, hidden = false }: Props = $props();
  const installed = resource((c) => c.mcp.servers(), ["mcp"]);
  const hasSettings = $derived(settings && !!installed.data?.find((s) => s.name === server.name)?.settings);
  let configuring = $state(false);
</script>

{#if configuring}
  <PluginSettingsDialog plugin={server.name} onclose={() => (configuring = false)} />
{:else}
  <Modal
    title={t("chat.setUp", { name: pluginLabel(server.name) })}
    description={server.description}
    width={600}
    onclose={onhide ?? ondone}
    closeLabel={onhide ? t("pending.hide") : undefined}
    {hidden}
  >
    {#if hasSettings}
      <div>
        <button class="btn btn--neutral btn--sm" onclick={() => (configuring = true)}
          ><SlidersHorizontal size={14} />{t("pluginSettings.open")}</button
        >
      </div>
    {/if}
    <PluginSetup {server} />
    {#snippet footer()}
      <button class="btn btn--primary" onclick={ondone}>{t("common.done")}</button>
    {/snippet}
  </Modal>
{/if}
