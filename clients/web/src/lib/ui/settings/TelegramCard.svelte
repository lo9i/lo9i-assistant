<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  const { client } = useDaemon();
  const loaded = resource((c) => c.telegram.status(), ["integrations"]);
  const s = $derived(loaded.data);
  let token = $state("");
  let error = $state("");

  async function act(action: () => Promise<unknown>): Promise<void> {
    try {
      await action();
      error = "";
    } catch (e) {
      error = describe(e);
    }
    loaded.reload();
  }

  function until(iso: string): string {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
</script>

<SettingsCard id="telegram" title="Telegram" sub="Talk to the assistant from Telegram, with its own conversation.">
  {#snippet status()}
    {#if s?.connected}
      <span class="pill" class:pill--accent={s.bot_running}>
        <span class="status-dot" style:--tone={s.bot_running ? "var(--color-success)" : "var(--color-warn)"}></span>
        {s.bot_running ? "Running" : "Starting"}
      </span>
    {/if}
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else if !s.connected}
    <ol class="steps">
      <li>In Telegram, open <strong>@BotFather</strong> and send <code>/newbot</code>.</li>
      <li>Choose a name, then a username ending in <code>bot</code>.</li>
      <li>BotFather replies with a token like <code>123456789:AAH…</code>. Paste it here.</li>
    </ol>
    <form
      class="row"
      onsubmit={(e) => {
        e.preventDefault();
        if (token.trim()) void act(() => client.telegram.connect(token.trim()));
      }}
    >
      <input class="input" bind:value={token} placeholder="Bot token" aria-label="Bot token" />
      <button class="btn btn--primary" type="submit">Connect</button>
    </form>
  {:else}
    <dl>
      <dt class="micro-label">Bot</dt>
      <dd>@{s.bot_username}</dd>
      <dt class="micro-label">Paired</dt>
      <dd>{s.paired_users.length ? s.paired_users.join(", ") : "No account yet"}</dd>
    </dl>
    {#if s.pairing_code}
      <div class="pairing">
        <p>
          Open <a href="https://t.me/{s.bot_username}" target="_blank" rel="noreferrer">t.me/{s.bot_username}</a>, press
          <strong>Start</strong>, and send this code:
        </p>
        <code class="code">{s.pairing_code}</code>
        <p class="text-caption">Valid until {until(s.pairing_expires)}.</p>
      </div>
    {/if}
    <div class="row">
      {#if !s.pairing_code}
        <button class="btn btn--neutral" onclick={() => act(() => client.telegram.startPairing())}>New pairing code</button>
      {/if}
      <button class="btn btn--danger" onclick={() => act(() => client.telegram.disconnect())}>Disconnect</button>
    </div>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SettingsCard>

<style>
  .steps {
    margin: 0;
    padding-left: 20px;
    display: flex;
    flex-direction: column;
    gap: 4px;
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
  dd {
    margin: 0;
  }
  .pairing {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    padding: 16px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-accent) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  }
  .pairing p {
    margin: 0;
  }
  .code {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.1em;
  }
</style>
