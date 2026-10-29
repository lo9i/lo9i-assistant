<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import Mail from "@lucide/svelte/icons/mail";
  import type { EmailAccount } from "$lib/api/types";
  import { alertOptions } from "$lib/channels";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import Confirm from "../Confirm.svelte";
  import EmailAccountForm from "./EmailAccountForm.svelte";

  // `channels`: the installed chat channels, where new mail can be announced.
  let { account, channels, open = false }: { account: EmailAccount; channels: string[]; open?: boolean } = $props();
  const alerts = $derived(alertOptions(channels, account.new_mail_alerts));

  const { client } = useDaemon();
  // svelte-ignore state_referenced_locally
  let expanded = $state(open || account.status !== "ok");
  let editing = $state(false);
  let renaming = $state(false);
  // svelte-ignore state_referenced_locally
  let name = $state(account.label);
  let confirming = $state(false);
  let message = $state("");

  /** Stays open with the error when the name can't be used. */
  async function rename(): Promise<void> {
    try {
      await client.email.rename(account.id, name);
      renaming = false;
      message = t("email.renamed");
    } catch (e) {
      message = describe(e);
    }
  }

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
      {#if account.status !== "ok"}<span class="pill pill--warn">{t("email.needsSignIn")}</span>{/if}
      {#if account.default}<span class="pill pill--accent">{t("email.default")}</span>{/if}
    </span>
    <span class="chevron" class:turned={expanded}><ChevronRight size={18} /></span>
  </button>
  {#if expanded}
    <div class="body">
      {#if account.status !== "ok"}<p class="warn">{account.problem}</p>{/if}
      {#if editing}
        <EmailAccountForm
          plugin={account.plugin}
          {account}
          onsaved={() => {
            editing = false;
            message = t("email.connected");
          }}
          oncancel={() => (editing = false)}
        />
      {:else}
        <dl>
          <dt class="micro-label">{t("email.server")}</dt>
          <dd>{account.host}:{account.port}</dd>
          <dt class="micro-label">{t("email.reading")}</dt>
          <dd>{account.imap_host ? t("email.readsFrom", { host: account.imap_host }) : t("email.sendingOnly")}</dd>
        </dl>
        {#if account.imap_host}
          <label class="fields">
            <span class="text-label">{t("email.alerts")}</span>
            <select
              class="input"
              value={account.new_mail_alerts}
              aria-label={t("email.alertsFor", { account: account.label })}
              onchange={(e) => act(() => client.email.setNewMailAlerts(account.id, e.currentTarget.value), t("email.saved"))}
            >
              {#each alerts as a (a.value)}
                <option value={a.value}>{a.label}</option>
              {/each}
            </select>
          </label>
        {/if}
        {#if renaming}
          <form
            class="row"
            onsubmit={(e) => {
              e.preventDefault();
              void rename();
            }}
          >
            <input
              class="input"
              bind:value={name}
              placeholder={t("email.renamePlaceholder")}
              aria-label={t("email.nameFor", { account: account.label })}
            />
            <button class="btn btn--primary" type="submit">{t("email.saveName")}</button>
            <button class="btn btn--ghost" type="button" onclick={() => (renaming = false)}>{t("common.cancel")}</button>
          </form>
        {/if}
        <div class="row">
          {#if !renaming}
            <button
              class="btn btn--neutral btn--sm"
              onclick={() => {
                name = account.label;
                renaming = true;
              }}>{t("email.rename")}</button
            >
          {/if}
          {#if !account.default}
            <button class="btn btn--neutral btn--sm" onclick={() => act(() => client.email.makeDefault(account.id), "")}
              >{t("email.makeDefault")}</button
            >
          {/if}
          <button class="btn btn--neutral btn--sm" onclick={() => (editing = true)}>{t("email.changeSignIn")}</button>
          <button class="btn btn--danger btn--sm" onclick={() => (confirming = true)}>{t("common.remove")}</button>
        </div>
      {/if}
      {#if message}<p class="text-meta">{message}</p>{/if}
    </div>
  {/if}
</div>

{#if confirming}
  <Confirm
    title={t("email.removeTitle", { account: account.label })}
    text={t("email.removeText", { address: account.sender })}
    action={t("common.remove")}
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
