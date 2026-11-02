<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import type { PluginUpdate } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { pluginLabel } from "$lib/plugins";
  import { needsValues } from "$lib/pluginUpdates";
  import UpdateValuesDialog from "./UpdateValuesDialog.svelte";

  // On an app's icon in the sidebar while its plugin has a newer version: pressing it updates the plugin there, without
  // going to Plugins. It spins while it updates; a new version that asks for a value opens a dialog for it, and any
  // other failure says why in a notice. At the row's right end, where a conversation's close button is; on the
  // icon's corner while the sidebar shows only icons.
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
    notices.notify(t("pluginsPage.updated", { names: pluginLabel(update.name) }));
  }

  const hint = $derived(
    busy
      ? t("pluginUpdates.updating", { name: pluginLabel(update.name) })
      : t("pluginUpdates.available", { from: update.installed_version || "–", to: update.version }),
  );
</script>

{#if done !== update.version}
  <button class="app-update" class:busy draggable="false" disabled={busy} title={hint} aria-label={hint} onclick={run}>
    <span class="dot"
      >{#if busy}<LoaderCircle size={12} class="spin" />{:else}<ArrowUp size={12} strokeWidth={3} />{/if}</span
    >
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
    top: 50%;
    right: 6px;
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    padding: 0;
    transform: translateY(-50%);
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    cursor: pointer;
  }
  .app-update:hover:not(.busy) {
    background: var(--color-bg-hover-ghost);
  }
  .app-update.busy {
    cursor: progress;
  }
  .dot {
    display: grid;
    place-items: center;
    width: 18px;
    height: 18px;
    border-radius: var(--radius-full);
    background: var(--color-accent);
    color: #fff;
  }
  /* Only the icons show: on the icon's corner, as the counts are. */
  :global(.collapsed) .app-update {
    top: 2px;
    right: auto;
    left: calc(50% + 2px);
    width: 18px;
    height: 18px;
    transform: none;
  }
  :global(.collapsed) .app-update:hover:not(.busy) {
    background: none;
  }
  :global(.collapsed) .dot {
    width: 14px;
    height: 14px;
  }
  @media (max-width: 680px) {
    .app-update {
      top: 2px;
      right: auto;
      left: calc(50% + 2px);
      width: 18px;
      height: 18px;
      transform: none;
    }
    .app-update:hover:not(.busy) {
      background: none;
    }
    .dot {
      width: 14px;
      height: 14px;
    }
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
