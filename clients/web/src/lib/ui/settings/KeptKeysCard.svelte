<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describeKept, keptName } from "$lib/keptKeys.svelte";
  import type { KeptKeys } from "$lib/api/types";
  import Confirm from "../Confirm.svelte";
  import SettingsCard from "../Card.svelte";

  // What removed plugins left kept, encrypted on the assistant's computer: their keys, used again when one is
  // installed again, and private repositories' tokens nothing needs any more. Deleting is for good.
  const { client, notices } = useDaemon();
  const kept = resource((c) => c.repositories.keptKeys(), ["plugins", "mcp", "skills", "settings"]);
  let deleting = $state<KeptKeys | null>(null);

  async function remove(entry: KeptKeys): Promise<void> {
    try {
      await client.repositories.forgetKeys(entry);
      notices.notify(`Deleted ${entry.plugin ? `the keys of ${entry.plugin}` : `the token for ${entry.repository_name}`}.`);
    } catch (e) {
      notices.report(e);
    }
    kept.reload();
  }
</script>

<SettingsCard id="kept-keys" title="Kept keys" sub="What removed plugins left, encrypted on the assistant's computer.">
  {#snippet status()}
    <span class="pill">{kept.data === undefined ? "…" : kept.data.length || "None"}</span>
  {/snippet}
  {#if kept.data === undefined}
    <p class="text-meta">{kept.error ?? "Loading…"}</p>
  {:else if !kept.data.length}
    <p class="text-meta">Nothing kept. Removing a plugin asks whether to keep its keys for installing it again.</p>
  {:else}
    <ul class="list">
      {#each kept.data as entry (entry.plugin + entry.repository)}
        <li>
          <div class="text">
            <strong>{keptName(entry)}</strong>
            <span class="text-meta">{entry.plugin ? describeKept(entry) : "No installed plugin needs it."}</span>
          </div>
          <button class="btn btn--danger btn--sm" onclick={() => (deleting = entry)}>Delete</button>
        </li>
      {/each}
    </ul>
  {/if}
</SettingsCard>

{#if deleting}
  {@const entry = deleting}
  <Confirm
    title="Delete {entry.plugin ? `the keys of ${entry.plugin}` : `the token for ${entry.repository_name}`}?"
    text={entry.plugin ? "Installing it again will ask for them again." : "Adding the repository again will ask for a token again."}
    action="Delete"
    onanswer={(yes) => {
      deleting = null;
      if (yes) void remove(entry);
    }}
  />
{/if}

<style>
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .list li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .text span {
    overflow-wrap: anywhere;
  }
</style>
