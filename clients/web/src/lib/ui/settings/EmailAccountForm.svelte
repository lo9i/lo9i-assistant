<script lang="ts">
  import type { EmailAccount, EmailProvider, EmailSettings } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";

  // "Other": the server is entered by hand.
  const OTHER = "other";
  const FIELDS: Array<{ key: Exclude<keyof EmailSettings, "port" | "imap_port" | "label">; label: string; type?: string }> = [
    { key: "host", label: "SMTP host" },
    { key: "username", label: "User name (usually your address)" },
    { key: "password", label: "App password (or account password, if your provider allows it)", type: "password" },
    { key: "sender", label: "Send as (your address)" },
    { key: "imap_host", label: "IMAP host, to read mail (TLS on port 993; leave empty to only send)" },
  ];

  type Props = {
    /** The account whose sign-in changes; a new account when absent. */
    account?: EmailAccount;
    onsaved: (account: EmailAccount) => void;
    oncancel?: () => void;
  };
  let { account, onsaved, oncancel }: Props = $props();

  const { client } = useDaemon();
  const providers = resource((c) => c.email.providers(), []);
  let choice = $state("");
  const provider = $derived<EmailProvider | undefined>(providers.data?.find((p) => p.id === choice));
  // svelte-ignore state_referenced_locally
  let label = $state(account?.label ?? "");
  // svelte-ignore state_referenced_locally
  let address = $state(account?.sender ?? "");
  let form = $state<EmailSettings>({ label: "", host: "", port: 587, username: "", password: "", sender: "", imap_host: "", imap_port: 993 });
  let message = $state("");
  let saving = $state(false);

  /** A provider's user name and sender are the address. */
  function settings(): EmailSettings {
    if (!provider) return { ...form, label };
    const { host, port, imap_host } = provider;
    return { label, host, port, imap_host, imap_port: 993, username: address, password: form.password, sender: address };
  }

  async function save(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    saving = true;
    try {
      onsaved(await (account ? client.email.update(account.id, settings()) : client.email.add(settings())));
    } catch (err) {
      message = describe(err);
    } finally {
      saving = false;
    }
  }
</script>

<div class="fields">
  <select class="input" bind:value={choice} aria-label="Mail provider">
    <option value="" disabled>Choose your provider</option>
    {#each providers.data ?? [] as p (p.id)}
      <option value={p.id}>{p.name}</option>
    {/each}
    <option value={OTHER}>Other (enter the server yourself)</option>
  </select>
  {#if provider}
    <p class="text-label">
      {provider.password_help}
      {#if provider.password_url}<a href={provider.password_url} target="_blank" rel="noreferrer">Create it here</a>.{/if}
    </p>
  {:else if choice === OTHER}
    <p class="text-label">Most providers need an <strong>app password</strong> here, not your account password.</p>
  {/if}
  {#if choice === OTHER || provider?.supported}
    <form class="fields" onsubmit={save}>
      <input class="input" placeholder="Name for this account, like Work (optional)" aria-label="Account name" bind:value={label} />
      {#if provider}
        <input class="input" type="email" placeholder="Your email address" aria-label="Your email address" bind:value={address} />
        <input class="input" type="password" placeholder="App password" aria-label="App password" bind:value={form.password} />
      {:else}
        {#each FIELDS as f (f.key)}
          <input class="input" type={f.type ?? "text"} placeholder={f.label} aria-label={f.label} bind:value={form[f.key]} />
        {/each}
        <input class="input" type="number" placeholder="Port (587, or 465)" aria-label="Port" bind:value={form.port} />
      {/if}
      {#if account}<p class="text-caption">Leave the password empty to keep the saved one.</p>{/if}
      <div class="row">
        <button class="btn btn--primary" type="submit" disabled={saving}>{saving ? "Checking…" : "Connect"}</button>
        {#if oncancel}<button class="btn btn--ghost" type="button" onclick={oncancel}>Cancel</button>{/if}
      </div>
    </form>
  {/if}
  {#if message}<p class="error-text">{message}</p>{/if}
</div>

<style>
  .fields {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .row {
    display: flex;
    gap: 8px;
  }
  p {
    margin: 0;
  }
</style>
