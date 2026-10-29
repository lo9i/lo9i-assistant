<script lang="ts">
  import Folder from "@lucide/svelte/icons/folder";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import { folderView, type FolderChoice } from "$lib/agentFolders";
  import type { AgentFolders, FolderListing } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import Modal from "../Modal.svelte";

  // /claude alone: the folder the agent works in, picked instead of typed. The workspace, the folders
  // used before, or browsing to one from the home folder. The daemon lists them: this browser may be on
  // another device. What it offers at each point is lib/agentFolders.ts.
  let { agentName, onpick }: { agentName: string; onpick: (folder: string | null) => void } = $props();
  const { client, notices } = useDaemon();
  let folders = $state<AgentFolders | null>(null);
  let listing = $state<FolderListing | null>(null);
  // Folders named with a dot (.config, .local) are left out unless the user asks.
  let showHidden = $state(false);
  const view = $derived(folderView(folders, listing));

  $effect(() => {
    client.conversations.agentFolders().then(
      (f) => (folders = f),
      (e) => notices.report(e),
    );
  });

  async function browse(path: string): Promise<void> {
    try {
      listing = await client.conversations.childFolders(path, showHidden);
    } catch (e) {
      notices.report(e);
    }
  }

  function choose(choice: FolderChoice): void {
    if (choice.action === "pick") onpick(choice.path);
    else void browse(choice.path);
  }

  const close = () => onpick(null);
</script>

<Modal title={t("folders.title", { agent: agentName })} description={view.description} onclose={close}>
  <div class="options">
    {#each view.choices as choice (choice.path + choice.label)}
      <button class="btn btn--neutral option" onclick={() => choose(choice)}>
        {#if choice.up}<ArrowUp size={16} />{:else}<Folder size={16} />{/if}
        {choice.label}
        {#if choice.detail}<span class="text-meta path">{choice.detail}</span>{/if}
      </button>
    {/each}
    {#if view.empty}<p class="text-meta">{t("folders.empty")}</p>{/if}
  </div>
  {#if listing}
    {@const here = listing.path}
    <label class="hidden-toggle text-meta">
      <input type="checkbox" bind:checked={showHidden} onchange={() => browse(here)} />
      {t("folders.showHidden")}
    </label>
  {/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={close}>{t("common.cancel")}</button>
    {#if view.primary}
      {@const primary = view.primary}
      <button class="btn btn--primary" onclick={() => choose(primary)}>{primary.label}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .options {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 50vh;
    overflow-y: auto;
  }
  .option {
    justify-content: flex-start;
    gap: 8px;
    overflow-wrap: anywhere;
    text-align: left;
  }
  .path {
    margin-left: auto;
  }
  .hidden-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 12px;
    cursor: pointer;
  }
</style>
