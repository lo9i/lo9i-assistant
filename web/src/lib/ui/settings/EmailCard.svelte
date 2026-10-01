<script lang="ts">
  import type { EmailProvider, EmailSettings } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  // "Other": the server is entered by hand.
  const OTHER = "other";
  const FIELDS: Array<{ key: keyof EmailSettings; label: string; type?: string }> = [
    { key: "host", label: "SMTP host" },
    { key: "port", label: "Port (587, or 465)", type: "number" },
    { key: "username", label: "User name (usually your address)" },
    { key: "password", label: "App password (or account password, if your provider allows it)", type: "password" },
    { key: "sender", label: "Send as (your address)" },
  ];

  const { client } = useDaemon();
  const loaded = resource((c) => c.email.status(), ["integrations"]);
  const providers = resource((c) => c.email.providers(), []);
  const s = $derived(loaded.data);
  let choice = $state("");
  const provider = $derived<EmailProvider | undefined>(providers.data?.find((p) => p.id === choice));
  let address = $state("");
  let form = $state<EmailSettings>({ host: "", port: 587, username: "", password: "", sender: "" });
  let recipients = $state("");
  let message = $state("");

  $effect(() => {
    recipients = (loaded.data?.allowed_recipients ?? []).join(", ");
  });

  /** A provider's user name and sender are the address. */
  function settings(): EmailSettings {
    if (!provider) return form;
    return { host: provider.host, port: provider.port, username: address, password: form.password, sender: address };
  }

  async function act(action: () => Promise<unknown>, done: string): Promise<void> {
    try {
      await action();
      message = done;
    } catch (e) {
      message = describe(e);
    }
    loaded.reload();
  }
</script>

<SettingsCard id="email" title="Email" sub="Lets the assistant send email. Anyone not listed needs your approval.">
  {#snippet status()}
    {#if s?.connected}<span class="pill pill--accent">Connected</span>{/if}
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else if !s.connected}
    <p class="text-label">Choose your mail provider. The assistant sends from your account through the provider's SMTP server.</p>
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
      <form
        class="fields"
        onsubmit={(e) => {
          e.preventDefault();
          void act(() => client.email.connect(settings()), "Connected ✓ The login worked.");
        }}
      >
        {#if provider}
          <input class="input" type="email" placeholder="Your email address" aria-label="Your email address" bind:value={address} />
          <input class="input" type="password" placeholder="App password" aria-label="App password" bind:value={form.password} />
        {:else}
          {#each FIELDS as f (f.key)}
            {#if f.key === "port"}
              <input class="input" type="number" placeholder={f.label} aria-label={f.label} bind:value={form.port} />
            {:else}
              <input class="input" type={f.type ?? "text"} placeholder={f.label} aria-label={f.label} bind:value={form[f.key]} />
            {/if}
          {/each}
        {/if}
        <div><button class="btn btn--primary" type="submit">Connect</button></div>
      </form>
    {/if}
  {:else}
    <dl>
      <dt class="micro-label">Sends as</dt>
      <dd>{s.sender}</dd>
      <dt class="micro-label">Server</dt>
      <dd>{s.host}:{s.port}</dd>
    </dl>
    <label class="fields">
      <span class="text-label">Sends without asking to you and:</span>
      <div class="row">
        <input class="input" bind:value={recipients} placeholder="Addresses, comma-separated" aria-label="Allowed recipients" />
        <button class="btn btn--neutral" onclick={() => act(() => client.email.setRecipients(recipients.split(",")), "Saved.")}>Save</button>
      </div>
    </label>
    <div><button class="btn btn--danger" onclick={() => act(() => client.email.disconnect(), "")}>Disconnect</button></div>
  {/if}
  {#if message}<p class="text-meta">{message}</p>{/if}
</SettingsCard>

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
</style>
