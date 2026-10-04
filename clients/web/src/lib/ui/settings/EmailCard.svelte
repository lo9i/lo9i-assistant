<script lang="ts">
  import Mail from "@lucide/svelte/icons/mail";
  import Plus from "@lucide/svelte/icons/plus";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";
  import EmptyState from "../EmptyState.svelte";
  import EmailAccountForm from "./EmailAccountForm.svelte";
  import EmailAccountRow from "./EmailAccountRow.svelte";

  const { client } = useDaemon();
  const accounts = resource((c) => c.email.accounts(), ["integrations"]);
  // Where new mail can be announced.
  const channels = resource((c) => c.channels.list(), ["channels"]);
  const channelNames = $derived((channels.data ?? []).map((c) => c.name));
  const allowed = resource((c) => c.email.recipients(), ["integrations"]);
  let adding = $state(false);
  let added = $state<string | null>(null);
  let recipients = $state("");
  let saved = $state("");

  $effect(() => {
    recipients = allowed.data?.join(", ") ?? "";
  });

  async function saveRecipients(): Promise<void> {
    try {
      await client.email.setRecipients(recipients.split(","));
      saved = "Saved.";
    } catch (e) {
      saved = describe(e);
    }
  }
</script>

<SettingsCard
  id="email"
  title="Email"
  sub="Lets the assistant send and read email, from one or more accounts. Sending to anyone not listed needs your approval."
>
  {#snippet status()}
    {#if accounts.data?.length}
      <span class="pill pill--accent">{accounts.data.length} {accounts.data.length === 1 ? "account" : "accounts"}</span>
    {/if}
  {/snippet}
  {#if accounts.data === undefined}
    <p class="text-meta">{accounts.error ?? "Loading…"}</p>
  {:else}
    {#if accounts.data.length}
      <div class="list">
        {#each accounts.data as account (account.id)}
          <EmailAccountRow {account} channels={channelNames} open={account.id === added} />
        {/each}
      </div>
      <label class="fields">
        <span class="text-label">Sends without asking, from any account, to your accounts and:</span>
        <div class="row">
          <input class="input" bind:value={recipients} placeholder="Addresses, comma-separated" aria-label="Allowed recipients" />
          <button class="btn btn--neutral" onclick={saveRecipients}>Save</button>
        </div>
        {#if saved}<span class="text-meta">{saved}</span>{/if}
      </label>
    {:else if !adding}
      <EmptyState icon={Mail} title="No email account yet" text="Connect one so the assistant can send and read mail for you." />
    {/if}
    {#if adding}
      <div class="add">
        <h3 class="text-heading">Add an email account</h3>
        <EmailAccountForm
          onsaved={(account) => {
            adding = false;
            added = account.id;
            accounts.reload();
          }}
          oncancel={() => (adding = false)}
        />
      </div>
    {:else}
      <div><button class="btn btn--neutral" onclick={() => (adding = true)}><Plus size={16} />Add an account</button></div>
    {/if}
  {/if}
</SettingsCard>

<style>
  .list {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }
  .fields {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .add {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  p,
  h3 {
    margin: 0;
  }
</style>
