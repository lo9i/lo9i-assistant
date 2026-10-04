<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import KeyRound from "@lucide/svelte/icons/key-round";
  import Laptop from "@lucide/svelte/icons/laptop";
  import Link from "@lucide/svelte/icons/link";
  import type { Device, PairingCode } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import Confirm from "$lib/ui/Confirm.svelte";
  import { clientLabel, conversationLabel } from "$lib/sessions";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { client, notices } = useDaemon();
  const devices = resource((c) => c.devices.list(), ["devices"]);
  const me = resource((c) => c.auth.me(), []);
  const clients = resource((c) => c.clients.list(), ["clients"]);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  // Links from other pages (Active sessions, Conversations) pick a device with ?d=<device id>.
  let picked = $state<string | null>(page.url.searchParams.get("d"));
  let code = $state<PairingCode | null>(null);
  let revoking = $state<Device | null>(null);
  // Until one is picked: this browser, or the first one.
  const device = $derived(devices.data?.find((d) => d.id === picked) ?? devices.data?.find((d) => isMe(d)) ?? devices.data?.[0]);

  const sessions = $derived((clients.data ?? []).filter((c) => c.device_id && c.device_id === device?.id));

  function sessionCount(d: Device): number {
    return (clients.data ?? []).filter((c) => c.device_id === d.id).length;
  }

  function isMe(d: Device): boolean {
    return d.id === me.data?.device?.id;
  }

  function when(iso: string): string {
    return new Date(iso).toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  async function pair(): Promise<void> {
    try {
      code = await client.devices.openPairing();
    } catch (e) {
      notices.report(e);
    }
  }

  // The sidebar's + links here with ?pair: open a code, then drop the parameter so a reload doesn't open another.
  $effect(() => {
    if (!page.url.searchParams.has("pair")) return;
    void pair();
    void goto(resolve("/devices"), { replaceState: true });
  });

  async function revoke(d: Device): Promise<void> {
    try {
      await client.devices.revoke(d.id);
    } catch (e) {
      return notices.report(e);
    }
    // Revoking this browser logs it out; the layout shows the pairing page.
    if (isMe(d)) location.reload();
  }
</script>

<TopBar title="Devices">
  {#snippet actions()}
    <button class="btn btn--primary" onclick={pair}><Link size={16} /><span class="hide-narrow">Pair a browser</span></button>
  {/snippet}
</TopBar>

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Paired browsers</h2>
        <p class="text-meta">Browsers allowed to use the assistant over the network. Click one to see it on the right.</p>
      </div>
      {#if devices.data}<span class="pill">{devices.data.length}</span>{/if}
    </header>
    <div class="scroll">
      {#if devices.error}
        <p class="error-text pad">{devices.error}</p>
      {:else if devices.data?.length === 0}
        <EmptyState icon={Laptop} title="No browsers paired" text="Pair a browser to use the assistant from another device." />
      {:else if devices.data && device}
        <table class="data-table">
          <thead>
            <tr>
              <th>Browser</th>
              <th>Sessions</th>
              <th>Last used</th>
              <th class="hide-narrow">From</th>
              <th class="hide-narrow">Paired</th>
            </tr>
          </thead>
          <tbody>
            {#each devices.data as d (d.id)}
              <tr class:selected={d.id === device.id} onclick={() => (picked = d.id)}>
                <td>
                  <button class="row-button" onclick={() => (picked = d.id)}>{d.name}</button>
                  {#if isMe(d)}<span class="pill pill--accent">This browser</span>{/if}
                </td>
                <td class="text-label">{sessionCount(d) || "—"}</td>
                <td class="text-label">{when(d.last_used_at)}</td>
                <td class="text-label hide-narrow">{d.last_ip || "—"}</td>
                <td class="text-label hide-narrow">{when(d.created_at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </section>

  <div class="column">
    {#if code}
      <section class="details pairing surface--glass">
        <header>
          <h2 class="text-heading">Pairing code</h2>
          <button class="btn btn--ghost btn--sm" onclick={() => (code = null)}>Hide</button>
        </header>
        <p>On the other device, open this page's address and enter:</p>
        <code class="code">{code.code}</code>
        <p class="text-caption">It works once, until {when(code.expires_at)}.</p>
      </section>
    {/if}
    {#if device}
      <section class="details surface--glass">
        <header>
          <h2 class="text-heading">{device.name}</h2>
          {#if isMe(device)}<span class="pill pill--accent">This browser</span>{/if}
        </header>
        <dl>
          <dt class="micro-label">Last used</dt>
          <dd>{when(device.last_used_at)}</dd>
          <dt class="micro-label">From</dt>
          <dd>{device.last_ip || "Unknown address"}</dd>
          <dt class="micro-label">Paired</dt>
          <dd>{when(device.created_at)}</dd>
        </dl>
        <div class="sessions">
          <h3 class="micro-label">Open sessions</h3>
          {#each sessions as c (`${c.id}-${c.connected_at}`)}
            <p>
              {clientLabel(c)} ·
              {#if c.thread_id}
                <a href="{resolve('/conversations')}?c={c.thread_id}">{conversationLabel(c, conversations.data)}</a>
              {:else}
                <span class="text-caption">{conversationLabel(c, conversations.data)}</span>
              {/if}
            </p>
          {:else}
            <p class="text-caption">None right now.</p>
          {/each}
        </div>
        <button class="btn btn--danger btn--sm revoke" onclick={() => (revoking = device)}>
          {isMe(device) ? "Log out" : "Revoke"}
        </button>
      </section>
    {:else if !code}
      <section class="details surface--glass">
        <EmptyState icon={KeyRound} title="No browser selected" text="Pick one from the table, or pair a new one." />
      </section>
    {/if}
  </div>
</div>

{#if revoking}
  {@const d = revoking}
  <Confirm
    title={isMe(d) ? "Log out of this browser?" : `Revoke ${d.name}?`}
    text="It will need a new code to use the assistant again."
    action={isMe(d) ? "Log out" : "Revoke"}
    onanswer={(yes) => {
      // `d` follows `revoking`: read it before clearing that.
      const device = d;
      revoking = null;
      if (yes) void revoke(device);
    }}
  />
{/if}

<style>
  .screen {
    display: flex;
    /* Cards take the height of their content, up to the screen; long lists scroll inside. */
    align-items: flex-start;
    gap: 16px;
    padding: 16px;
    height: calc(100dvh - 76px);
    max-width: 1600px;
    margin: 0 auto;
  }
  /* The table takes three quarters of the width, the device the rest. */
  .table-card {
    flex: 3 1 0;
    min-width: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .column {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 16px 24px;
    min-height: 66px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .scroll {
    overflow-y: auto;
    min-height: 0;
  }
  .data-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .pad {
    padding: 24px;
  }
  tr {
    cursor: pointer;
  }
  tr.selected {
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
  }
  tr.selected td:first-child {
    box-shadow: inset 3px 0 0 var(--color-accent);
  }
  td .pill {
    margin-left: 8px;
  }
  .row-button {
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    cursor: pointer;
  }
  .details {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
  }
  .details header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .details p {
    margin: 0;
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
    text-align: right;
  }
  .sessions {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .sessions h3 {
    margin: 0 0 2px;
  }
  .revoke {
    align-self: flex-start;
  }
  .pairing {
    background: color-mix(in srgb, var(--color-accent) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  }
  .code {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.1em;
  }
  /* Stacked, the page scrolls: each part takes its own height instead of a share of the screen. */
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
      align-items: stretch;
      height: auto;
    }
    .table-card,
    .column {
      flex: none;
    }
  }
</style>
