<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import Mail from "@lucide/svelte/icons/mail";
  import type { EmailAccount } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import Confirm from "../Confirm.svelte";
  import EmailAccountForm from "./EmailAccountForm.svelte";

  const ALERTS = [
    { value: "", label: "Don't announce" },
    { value: "telegram", label: "Telegram" },
    { value: "slack", label: "Slack" },
  ];

  let { account, open = false }: { account: EmailAccount; open?: boolean } = $props();

  const { client } = useDaemon();
  // svelte-ignore state_referenced_locally
  let expanded = $state(open || account.status !== "ok");
  let editing = $state(false);
  let confirming = $state(false);
  // svelte-ignore state_referenced_locally
  let recipients = $state(account.allowed_recipients.join(", "));
  let message = $state("");

  async function act(action: () => Promise<unknown>, done: string): Promise<void> {
    try {
      await action();
      message = done;
    } catch (e) {
      message = describe(e);
    }
  }
</script>

<div class="account">
  <button class="head" aria-expanded={expanded} onclick={() => (expanded = !expanded)}>
    <span class="tile"><Mail size={16} /></span>
    <span class="text">
      <strong>{account.label}</strong>
      <span class="text-meta">{account.sender}</span>
    </span>
    <span class="pills">
      {#if account.status !== "ok"}<span class="pill pill--warn">Needs sign-in</span>{/if}
      {#if account.default}<span class="pill pill--accent">Default</span>{/if}
    </span>
    <span class="chevron" class:turned={expanded}><ChevronRight size={18} /></span>
  </button>
  {#if expanded}
    <div class="body">
      {#if account.status !== "ok"}<p class="warn">{account.problem}</p>{/if}
      {#if editing}
        <EmailAccountForm
          {account}
          onsaved={() => {
            editing = false;
            message = "Connected ✓ The login worked.";
          }}
          oncancel={() => (editing = false)}
        />
      {:else}
        <dl>
          <dt class="micro-label">Server</dt>
          <dd>{account.host}:{account.port}</dd>
          <dt class="micro-label">Reading</dt>
          <dd>{account.imap_host ? `Reads mail from ${account.imap_host}` : "Sending only"}</dd>
        </dl>
        {#if account.imap_host}
          <label class="fields">
            <span class="text-label">New mail alerts</span>
            <select
              class="input"
              value={account.new_mail_alerts}
              aria-label="New mail alerts for {account.label}"
              onchange={(e) => act(() => client.email.setNewMailAlerts(account.id, e.currentTarget.value), "Saved.")}
            >
              {#each ALERTS as a (a.value)}
                <option value={a.value}>{a.label}</option>
              {/each}
            </select>
          </label>
        {/if}
        <label class="fields">
          <span class="text-label">Sends without asking to {account.sender} and:</span>
          <div class="row">
            <input class="input" bind:value={recipients} placeholder="Addresses, comma-separated" aria-label="Allowed recipients for {account.label}" />
            <button class="btn btn--neutral" onclick={() => act(() => client.email.setRecipients(account.id, recipients.split(",")), "Saved.")}>
              Save
            </button>
          </div>
        </label>
        <div class="row">
          {#if !account.default}
            <button class="btn btn--neutral btn--sm" onclick={() => act(() => client.email.makeDefault(account.id), "")}>Make default</button>
          {/if}
          <button class="btn btn--neutral btn--sm" onclick={() => (editing = true)}>Change sign-in</button>
          <button class="btn btn--danger btn--sm" onclick={() => (confirming = true)}>Remove</button>
        </div>
      {/if}
      {#if message}<p class="text-meta">{message}</p>{/if}
    </div>
  {/if}
</div>

{#if confirming}
  <Confirm
    title="Remove {account.label}?"
    text="The assistant stops sending and reading mail with {account.sender}. Its saved password is deleted."
    action="Remove"
    onanswer={(yes) => {
      confirming = false;
      if (yes) void act(() => client.email.remove(account.id), "");
    }}
  />
{/if}

<style>
  .account + :global(.account) {
    border-top: 1px solid var(--color-border);
  }
  .head {
    display: grid;
    grid-template-columns: 36px 1fr auto 20px;
    align-items: center;
    gap: 10px;
    width: 100%;
    min-height: 56px;
    padding: 10px 16px;
    border: 0;
    background: none;
    text-align: left;
    cursor: pointer;
    transition: background 0.12s ease;
  }
  .head:hover {
    background: color-mix(in srgb, var(--color-text-primary) 4%, transparent);
  }
  .tile {
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-text-primary) 8%, transparent);
    color: var(--color-text-muted);
  }
  .text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .pills {
    display: flex;
    gap: 6px;
  }
  .chevron {
    color: var(--color-text-faint);
    transition: transform 0.12s ease;
  }
  .turned {
    transform: rotate(90deg);
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 4px 16px 16px 62px;
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
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    margin: 0;
    align-items: baseline;
  }
  dd,
  p {
    margin: 0;
  }
  .warn {
    color: var(--color-warn);
  }
</style>
