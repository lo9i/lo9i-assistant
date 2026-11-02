<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import type { PluginUpdate } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { pageLabel } from "$lib/pages";
  import { needsValues } from "$lib/pluginUpdates";
  import UpdateValuesDialog from "./UpdateValuesDialog.svelte";

  // On an app's icon in the sidebar while its plugin has a newer version: pressing it updates the plugin there, without
  // going to Plugins. It spins while it updates; a new version that asks for a value opens a dialog for it, and any
  // other failure says why in a notice. The parent places it on the icon's corner.
  let { update }: { update: PluginUpdate } = $props();
  const { client, notices } = useDaemon();

  let busy = $state(false);
  // The version it was updated to: the badge goes at once, before the list of updates is read again.
  let done = $state("");
  let asking = $state("");

  async function run(): Promise<void> {
    busy = true;
    try {
      await client.mcp.updateFromRepository(update.name);
      finished();
    } catch (e) {
      if (needsValues(e)) asking = describe(e);
      else notices.report(e);
    } finally {
      busy = false;
    }
  }

  function finished(): void {
    done = update.version;
    notices.notify(t("pluginsPage.updated", { names: pageLabel(update.name) }));
  }

  const hint = $derived(
    busy
      ? t("pluginUpdates.updating", { name: pageLabel(update.name) })
      : t("pluginUpdates.available", { from: update.installed_version || "–", to: update.version }),
  );
</script>

{#if done !== update.version}
  <button class="app-update" class:busy draggable="false" disabled={busy} title={hint} aria-label={hint} onclick={run}>
    {#if busy}<LoaderCircle size={11} class="spin" />{:else}<ArrowUp size={11} strokeWidth={3} />{/if}
  </button>
{/if}

{#if asking}
  <UpdateValuesDialog
    plugin={update.name}
    reason={asking}
    onclose={(updated) => {
      asking = "";
      if (updated) finished();
    }}
  />
{/if}

<style>
  .app-update {
    position: absolute;
    top: 4px;
    left: 24px;
    display: grid;
    place-items: center;
    width: 16px;
    height: 16px;
    padding: 0;
    border: 2px solid var(--sidebar-bg);
    border-radius: var(--radius-full);
    box-sizing: content-box;
    background: var(--color-accent);
    color: #fff;
    cursor: pointer;
    transition: transform 0.12s ease;
  }
  /* A larger target than the dot it shows. */
  .app-update::before {
    content: "";
    position: absolute;
    inset: -6px;
  }
  .app-update:hover:not(.busy) {
    transform: scale(1.15);
  }
  .app-update.busy {
    cursor: progress;
  }
  .app-update :global(.spin) {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .app-update :global(.spin) {
      animation: none;
    }
  }
</style>
