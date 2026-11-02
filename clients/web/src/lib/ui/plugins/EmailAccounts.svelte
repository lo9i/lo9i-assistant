<script lang="ts">
  import Plus from "@lucide/svelte/icons/plus";
  import { resource } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import EmailAccountForm from "./EmailAccountForm.svelte";
  import EmailAccountRow from "./EmailAccountRow.svelte";

  // The email accounts of one email plugin, in its details.
  let { plugin, title }: { plugin: string; title: string } = $props();
  const accounts = resource((c) => c.email.accounts(), ["integrations", "mcp"]);
  const mine = $derived((accounts.data ?? []).filter((a) => a.plugin === plugin));
  // Where new mail can be announced.
  const channels = resource((c) => c.channels.list(), ["channels"]);
  const channelNames = $derived((channels.data ?? []).map((c) => c.name));
  let adding = $state(false);
  let added = $state<string | null>(null);
</script>

<section class="accounts" aria-label={title}>
  <h3 class="micro-label">{title}</h3>
  {#if accounts.data === undefined}
    <p class="text-meta">{accounts.error ?? t("common.loading")}</p>
  {:else}
    {#if mine.length}
      <div class="list">
        {#each mine as account (account.id)}
          <EmailAccountRow {account} channels={channelNames} open={account.id === added} />
        {/each}
      </div>
    {:else if !adding}
      <p class="text-meta">{t("email.noAccount")}</p>
    {/if}
    {#if adding}
      <!-- Framed with its own heading, so its Cancel reads as dropping this account, not closing the setup. -->
      <section class="new" aria-label={t("email.newAccount")}>
        <h4 class="text-heading">{t("email.newAccount")}</h4>
        <EmailAccountForm
          {plugin}
          onsaved={(account) => {
            adding = false;
            added = account.id;
            accounts.reload();
          }}
          oncancel={() => (adding = false)}
        />
      </section>
    {:else}
      <div><button class="btn btn--neutral btn--sm" onclick={() => (adding = true)}><Plus size={14} />{t("email.addAccount")}</button></div>
    {/if}
  {/if}
</section>

<style>
  .accounts {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-top: 16px;
    border-top: 1px solid var(--color-border);
  }
  /* Nothing above it to set it apart from (a dialog showing only the accounts). */
  .accounts:first-child {
    padding-top: 0;
    border-top: none;
  }
  .list {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }
  .new {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }
  h3,
  h4,
  p {
    margin: 0;
  }
</style>
