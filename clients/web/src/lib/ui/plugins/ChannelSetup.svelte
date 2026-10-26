<script lang="ts">
  import Copy from "@lucide/svelte/icons/copy";
  import type { ChannelStatus, SetupItem } from "$lib/api/types";
  import { lineOf, qrOf, stateOf, titleOf } from "$lib/channels";
  import { useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";

  // A chat channel's setup, in its plugin's details. Each channel sends what to show for setting it up
  // (its items), so this draws them without knowing any channel.
  let { channel }: { channel: ChannelStatus } = $props();
  const { client, notices } = useDaemon();
  let error = $state("");

  const TONES = { Off: "var(--color-text-muted)", Connected: "var(--color-success)", "Not connected": "var(--color-warn)" };
  const connection = $derived(stateOf(channel));
  const actions = $derived(channel.items.filter((i) => i.kind === "action"));

  async function press(item: SetupItem): Promise<void> {
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

<section class="channel" aria-label="{titleOf(channel.name)} setup">
  <header>
    <h3 class="micro-label">Setup</h3>
    <span class="pill" class:pill--accent={connection === "Connected"}>
      <span class="status-dot" style:--tone={TONES[connection]}></span>
      {connection}
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
    {:else if item.kind === "qr"}
      {@const qr = qrOf(item.value)}
      <figure class="qr-box">
        <svg viewBox="0 0 {qr.size} {qr.size}" shape-rendering="crispEdges" role="img" aria-label={item.label || "QR code"}>
          <rect width={qr.size} height={qr.size} fill="#fff" />
          <path d={qr.path} fill="#000" />
        </svg>
        {#if item.label}<figcaption class="micro-label">{item.label}</figcaption>{/if}
      </figure>
    {/if}
  {/each}
  {#if actions.length}
    <div class="row">
      {#each actions as item (item.value)}
        <button
          class="btn btn--neutral btn--sm"
          disabled={!channel.connected}
          title={channel.connected ? undefined : `${titleOf(channel.name)} isn't connected`}
          onclick={() => press(item)}>{item.label}</button
        >
      {/each}
    </div>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</section>

<style>
  .channel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-top: 16px;
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
  /* Black on white in both themes: phones read a QR code best that way. */
  .qr-box {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    margin: 0;
  }
  .qr-box svg {
    width: min(260px, 100%);
    height: auto;
    border-radius: var(--radius-sm);
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
