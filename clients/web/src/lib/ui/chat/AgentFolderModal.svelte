<script lang="ts">
  import Folder from "@lucide/svelte/icons/folder";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import type { AgentFolders, FolderListing } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import Modal from "../Modal.svelte";

  // /claude alone: the folder the agent works in, picked instead of typed. The workspace, the folders
  // used before, or browsing to one from the home folder. The daemon lists them: this browser may be on
  // another device.
  let { agentName, onpick }: { agentName: string; onpick: (folder: string | null) => void } = $props();
  const { client, notices } = useDaemon();
  let folders = $state<AgentFolders | null>(null);
  let listing = $state<FolderListing | null>(null);

  $effect(() => {
    client.conversations.agentFolders().then(
      (f) => (folders = f),
      (e) => notices.report(e),
    );
  });

  async function browse(path: string): Promise<void> {
    try {
      listing = await client.conversations.childFolders(path);
    } catch (e) {
      notices.report(e);
    }
  }

  const name = (path: string) => path.split("/").filter(Boolean).pop() ?? path;
  const close = () => onpick(null);
</script>

<Modal
  title="Where should {agentName} work?"
  description={listing ? listing.path : "The workspace, a folder used before, or browse to one."}
  onclose={close}
>
  <div class="options">
    {#if listing}
      {#if listing.parent}
        <button class="btn btn--neutral option" onclick={() => browse(listing!.parent!)}><ArrowUp size={16} /> Up</button>
      {/if}
      {#each listing.children as child (child)}
        <button class="btn btn--neutral option" onclick={() => browse(child)}><Folder size={16} /> {name(child)}</button>
      {:else}
        <p class="text-meta">No folders inside.</p>
      {/each}
    {:else if folders}
      <button class="btn btn--neutral option" onclick={() => onpick(folders!.workspace)}>
        <Folder size={16} /> Workspace <span class="text-meta path">{folders.workspace}</span>
      </button>
      {#each folders.recent as folder (folder)}
        <button class="btn btn--neutral option" onclick={() => onpick(folder)}><Folder size={16} /> {folder}</button>
      {/each}
    {/if}
  </div>
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={close}>Cancel</button>
    {#if listing}
      <button class="btn btn--primary" onclick={() => onpick(listing!.path)}>Use this folder</button>
    {:else if folders}
      <button class="btn btn--primary" onclick={() => browse(folders!.home)}>Browse…</button>
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
</style>
