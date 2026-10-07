<script lang="ts">
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import type { Repository } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import Confirm from "../Confirm.svelte";
  import Modal from "../Modal.svelte";
  import SecretInput from "../SecretInput.svelte";

  // The repositories Plugins lists plugins from. The assistant's extras are built in and the only
  // official one; others are added by their https:// address and removed here, which leaves what was
  // installed from them. A private one is added with a token that can read it, which goes straight to
  // the daemon and is kept encrypted. `onclose` says whether the list changed, so Plugins reads them again.
  type Props = { onclose: (changed: boolean) => void };
  let { onclose }: Props = $props();
  const { client, notices } = useDaemon();
  const repositories = resource((c) => c.repositories.list(), ["settings"]);

  let url = $state("");
  let token = $state("");
  let busy = $state(false);
  let error = $state("");
  let changed = $state(false);
  let removing = $state<Repository | null>(null);

  async function add(): Promise<void> {
    if (!url.trim()) return;
    busy = true;
    try {
      const added = await client.repositories.add(url.trim(), token.trim());
      notices.notify(`Added ${added.name}. Its plugins show in Plugins.`);
      url = "";
      token = "";
      error = "";
      changed = true;
      repositories.reload();
    } catch (e) {
      error = describe(e);
    } finally {
      busy = false;
    }
  }

  async function remove(repository: Repository): Promise<void> {
    try {
      await client.repositories.remove(repository.url);
      notices.notify(`Removed ${repository.name}. Plugins installed from it stay.`);
      changed = true;
    } catch (e) {
      notices.report(e);
    }
    repositories.reload();
  }
</script>

<Modal
  title="Repositories"
  description="Plugins are listed from these. Only the assistant's extras are official: what you install from another repository runs on this computer, so add only ones you trust."
  onclose={() => onclose(changed)}
>
  {#if repositories.error}
    <p class="error-text">{repositories.error}</p>
  {:else if repositories.data}
    <ul>
      {#each repositories.data as r (r.url)}
        <li>
          <div>
            <span class="name">{r.name}</span>
            {#if r.official}<span class="badge official">Official</span>{/if}
            {#if r.private}<span class="badge">Private</span>{/if}
            <p class="text-caption">{r.url}</p>
          </div>
          {#if !r.official}
            <button class="btn btn--ghost btn--sm" title="Remove {r.name}" onclick={() => (removing = r)}><Trash2 size={14} /></button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
  <form
    onsubmit={(e) => {
      e.preventDefault();
      void add();
    }}
  >
    <input class="input" bind:value={url} placeholder="https://github.com/you/your-plugins" aria-label="Repository address" />
    <SecretInput bind:value={token} label="Token, for a private repository" placeholder="Token (private only)" />
    <button class="btn btn--primary" disabled={busy || !url.trim()}>{busy ? "Reading…" : "Add"}</button>
  </form>
  <p class="text-caption">
    Git repositories by their https:// address. For a private one, give a token that can read its contents (on GitHub, a fine-grained token
    with Contents: read for that repository).
  </p>
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onclose(changed)}>Close</button>
  {/snippet}
</Modal>

{#if removing}
  {@const r = removing}
  <Confirm
    title="Remove {r.name}?"
    text={r.private
      ? "Its plugins stop showing in Plugins. The ones installed from it stay installed and keep updating from it, with its token, until you remove the last of them."
      : "Its plugins stop showing in Plugins. The ones installed from it stay installed and keep updating from it."}
    action="Remove"
    onanswer={(yes) => {
      removing = null;
      if (yes) void remove(r);
    }}
  />
{/if}

<style>
  ul {
    list-style: none;
    margin: 0 0 16px;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  li p {
    margin: 2px 0 0;
    overflow-wrap: anywhere;
  }
  .name {
    font-weight: 500;
  }
  .badge {
    margin-left: 8px;
    padding: 1px 6px;
    border-radius: 999px;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
    border: 1px solid var(--color-border);
  }
  .badge.official {
    color: var(--color-success);
    border-color: color-mix(in srgb, var(--color-success) 40%, transparent);
  }
  form {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  form > :global(*) {
    flex: 1 1 200px;
  }
  form > button {
    flex: 0 0 auto;
  }
  .text-caption {
    margin: 4px 0 0;
  }
</style>
