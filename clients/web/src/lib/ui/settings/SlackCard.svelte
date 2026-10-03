<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  const { client, notices } = useDaemon();
  const loaded = resource((c) => c.slack.status(), ["integrations"]);
  const s = $derived(loaded.data);
  let appToken = $state("");
  let botToken = $state("");
  let userToken = $state("");
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

  async function connect(): Promise<void> {
    if (!appToken.trim() || !botToken.trim() || !userToken.trim()) {
      error = "Paste all three tokens.";
      return;
    }
    await act(async () => {
      await client.slack.connect({
        app_token: appToken.trim(),
        bot_token: botToken.trim(),
        user_token: userToken.trim(),
      });
      appToken = botToken = userToken = "";
    });
  }

  async function copyManifest(): Promise<void> {
    try {
      await navigator.clipboard.writeText(await client.slack.manifest());
      notices.notify("Copied the manifest.");
    } catch (e) {
      notices.report(e);
    }
  }
</script>

<SettingsCard id="slack" title="Slack" sub="Talk to the assistant in a Slack DM, and let it read and post in your workspace.">
  {#snippet status()}
    {#if s?.connected}
      <span class="pill" class:pill--accent={s.running}>
        <span class="status-dot" style:--tone={s.running ? "var(--color-success)" : "var(--color-warn)"}></span>
        {s.running ? "Connected" : "Connecting"}
      </span>
    {/if}
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else if !s.connected}
    <ol class="steps">
      <li>
        Open <a href="https://api.slack.com/apps" target="_blank" rel="noreferrer">api.slack.com/apps</a>, choose
        <strong>Create New App → From a manifest</strong>, and pick your workspace.
      </li>
      <li>
        Paste the app manifest, then choose <strong>Next → Create</strong>.
        <div class="step-action">
          <button class="btn btn--neutral btn--sm" type="button" onclick={copyManifest}>Copy manifest</button>
        </div>
      </li>
      <li>
        In <strong>Basic Information → App-Level Tokens</strong>, choose <strong>Generate Token and Scopes</strong>, add the scope
        <code>connections:write</code>, and generate. Copy the token that starts with <code>xapp-</code>.
      </li>
      <li>
        In <strong>OAuth &amp; Permissions</strong>, choose <strong>Install to</strong> your workspace, then
        <strong>Allow</strong>. The same page then shows the <strong>Bot User OAuth Token</strong> (<code>xoxb-</code>) and the
        <strong>User OAuth Token</strong>
        (<code>xoxp-</code>).
      </li>
    </ol>
    <form
      class="fields"
      onsubmit={(e) => {
        e.preventDefault();
        void connect();
      }}
    >
      <input class="input" type="password" bind:value={appToken} placeholder="App token (xapp-…)" aria-label="App token" />
      <input
        class="input"
        type="password"
        bind:value={botToken}
        placeholder="Bot User OAuth Token (xoxb-…)"
        aria-label="Bot User OAuth Token"
      />
      <input class="input" type="password" bind:value={userToken} placeholder="User OAuth Token (xoxp-…)" aria-label="User OAuth Token" />
      <div class="row"><button class="btn btn--primary" type="submit">Connect</button></div>
    </form>
  {:else}
    <dl>
      <dt class="micro-label">Workspace</dt>
      <dd>{s.team}</dd>
      <dt class="micro-label">Answers</dt>
      <dd>{s.owner_name}</dd>
    </dl>
    <p class="text-caption">
      In Slack, open the app under <strong>Apps</strong> in the sidebar and send it a message. <code>/new</code> starts a new conversation.
    </p>
    <div class="row">
      <button class="btn btn--danger" onclick={() => act(() => client.slack.disconnect())}>Disconnect</button>
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
  .step-action {
    margin: 6px 0 2px;
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
  dd {
    margin: 0;
  }
  p {
    margin: 0;
  }
</style>
