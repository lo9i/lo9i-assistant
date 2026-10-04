<script lang="ts">
  import { resolve } from "$app/paths";
  import Copy from "@lucide/svelte/icons/copy";
  import type { ChannelStatus, SetupItem } from "$lib/api/types";
  import { lineOf, stateOf, titleOf } from "$lib/channels";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  // Each channel sends what to show for setting it up (its items), so this card draws them without
  // knowing any channel. The `channels` event comes when a channel connects or changes its items.
  const { client, notices } = useDaemon();
  const loaded = resource((c) => c.channels.list(), ["channels"]);
  let error = $state("");

  const TONES = { Off: "var(--color-text-muted)", Connected: "var(--color-success)", "Not connected": "var(--color-warn)" };

  async function press(channel: ChannelStatus, item: SetupItem): Promise<void> {
    try {
      await client.channels.press(channel.name, item.value);
      error = "";
    } catch (e) {
      error = describe(e);
    }
  }

  async function copy(item: SetupItem): Promise<void> {
    try {
      await navigator.clipboard.writeText(item.value);
      notices.notify(`Copied ${item.label ? item.label.toLowerCase() : "it"}.`);
    } catch (e) {
      notices.report(e);
    }
  }
</script>

<SettingsCard id="channels" title="Channels" sub="Talk to the assistant from other chat apps, each with its own conversation.">
  {#if loaded.data === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else if loaded.data.length === 0}
    <p class="text-meta">
      No channel is installed. Install Telegram or Slack from <a href={resolve("/plugins")}>Plugins</a>, then set it up here.
    </p>
  {:else}
    {#each loaded.data as channel (channel.name)}
      {@const state = stateOf(channel)}
      {@const actions = channel.items.filter((i) => i.kind === "action")}
      <section class="channel" aria-label={titleOf(channel.name)}>
        <header>
          <h3 class="text-label">{titleOf(channel.name)}</h3>
          <span class="pill" class:pill--accent={state === "Connected"}>
            <span class="status-dot" style:--tone={TONES[state]}></span>
            {state}
          </span>
        </header>
        {#each channel.items as item, i (i)}
          {#if item.kind === "text"}
            <p>{lineOf(item)}</p>
          {:else if item.kind === "code"}
            <div class="code-box">
              {#if item.label}<span class="micro-label">{item.label}</span>{/if}
              <code class="code">{item.value}</code>
            </div>
          {:else if item.kind === "copy"}
            <div class="copy-box">
              <div class="copy-head">
                <span class="micro-label">{item.label}</span>
                <button class="btn btn--neutral btn--sm" type="button" onclick={() => copy(item)}><Copy size={14} />Copy</button>
              </div>
              <pre>{item.value}</pre>
            </div>
          {/if}
        {/each}
        {#if actions.length}
          <div class="row">
            {#each actions as item (item.value)}
              <button
                class="btn btn--neutral btn--sm"
                disabled={!channel.connected}
                title={channel.connected ? undefined : `${titleOf(channel.name)} isn't connected`}
                onclick={() => press(channel, item)}>{item.label}</button
              >
            {/each}
          </div>
        {/if}
      </section>
    {/each}
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SettingsCard>

<style>
  .channel {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .channel + .channel {
    padding-top: 24px;
    border-top: 1px solid var(--color-border);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  h3,
  p {
    margin: 0;
  }
  .code-box {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    padding: 16px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-accent) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  }
  .code {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.1em;
  }
  .copy-box {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }
  .copy-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  pre {
    margin: 0;
    max-height: 200px;
    overflow: auto;
    padding: 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-border);
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
</style>
