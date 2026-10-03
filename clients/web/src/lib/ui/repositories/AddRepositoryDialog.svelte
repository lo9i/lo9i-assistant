<script lang="ts">
  import { useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import Modal from "../Modal.svelte";

  let { onclose }: { onclose: (added?: string) => void } = $props();
  const { client } = useDaemon();
  let url = $state("");
  let busy = $state(false);
  let error = $state("");

  async function add(): Promise<void> {
    busy = true;
    try {
      await client.repositories.add(url.trim());
      onclose(url.trim());
    } catch (e) {
      error = describe(e);
    } finally {
      busy = false;
    }
  }
</script>

<Modal
  title="Add a repository"
  description="A git repository with plugins: MCP servers (folders with a server.yaml) and skills (folders with a SKILL.md). Its plugins show up in the list."
  width={520}
  onclose={() => onclose()}
>
  <label class="field">
    <span class="micro-label">Repository</span>
    <input class="input" bind:value={url} placeholder="https://github.com/user/extras" autocomplete="off" />
  </label>
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onclose()}>Cancel</button>
    <button class="btn btn--primary" disabled={busy || !url.trim()} onclick={add}>{busy ? "Reading it…" : "Add"}</button>
  {/snippet}
</Modal>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  p {
    margin: 0;
  }
</style>
