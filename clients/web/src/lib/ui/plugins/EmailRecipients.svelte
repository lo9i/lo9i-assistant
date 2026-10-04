<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";

  // Who the assistant emails without asking, from any account, in the Communications category.
  const { client } = useDaemon();
  const allowed = resource((c) => c.email.recipients(), ["integrations"]);
  let recipients = $state("");
  let saved = $state("");

  $effect(() => {
    recipients = allowed.data?.join(", ") ?? "";
  });

  async function save(): Promise<void> {
    try {
      await client.email.setRecipients(recipients.split(","));
      saved = "Saved.";
    } catch (e) {
      saved = describe(e);
    }
  }
</script>

<section class="recipients" aria-label="Allowed recipients">
  <h3 class="micro-label">Allowed recipients</h3>
  <label class="fields">
    <span class="text-label">Sends without asking, from any account, to your accounts and:</span>
    <div class="row">
      <input class="input" bind:value={recipients} placeholder="Addresses, comma-separated" aria-label="Allowed recipients" />
      <button class="btn btn--neutral btn--sm" onclick={save}>Save</button>
    </div>
    {#if saved}<span class="text-meta">{saved}</span>{/if}
  </label>
</section>

<style>
  .recipients,
  .fields {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .recipients {
    gap: 12px;
  }
  .row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  h3 {
    margin: 0;
  }
</style>
