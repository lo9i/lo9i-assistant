<script lang="ts">
  import Globe from "@lucide/svelte/icons/globe";
  import MonitorSmartphone from "@lucide/svelte/icons/monitor-smartphone";
  import SquareTerminal from "@lucide/svelte/icons/square-terminal";
  import { resolve } from "$app/paths";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { clientLabel, conversationLabel, deviceLabel } from "$lib/sessions";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { client } = useDaemon();
  const clients = resource((c) => c.clients.list(), ["clients"]);
  const devices = resource((c) => c.devices.list(), ["devices"]);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const ICONS = { web: Globe, cli: SquareTerminal };
</script>

<TopBar title="Active sessions" />

<div class="shell">
  <section class="surface--glass card">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Connected clients</h2>
        <p class="text-meta">Each terminal and browser tab has its own conversation. Click a device or conversation to open it.</p>
      </div>
      {#if clients.data}<span class="pill">{clients.data.length}</span>{/if}
    </header>
    {#if clients.error}
      <p class="error-text pad">{clients.error}</p>
    {:else if clients.data?.length === 0}
      <EmptyState icon={MonitorSmartphone} title="No clients" text="Clients show up here while they're connected." />
    {:else if clients.data}
      <table class="data-table">
        <thead>
          <tr>
            <th>Client</th>
            <th>Device</th>
            <th>Conversation</th>
            <th class="hide-narrow">Connection</th>
            <th class="hide-narrow">Connected since</th>
          </tr>
        </thead>
        <tbody>
          {#each clients.data as c (`${c.id}-${c.transport}-${c.connected_at}`)}
            {@const Icon = ICONS[c.kind as keyof typeof ICONS] ?? MonitorSmartphone}
            <tr>
              <td>
                <span class="client"><Icon size={16} />{clientLabel(c)}</span>
                {#if c.id === client.clientId}<span class="pill pill--accent">This tab</span>{/if}
              </td>
              <td>
                {#if c.device_id}
                  <a href="{resolve('/devices')}?d={c.device_id}">{deviceLabel(c, devices.data)}</a>
                {:else}
                  <span class="text-label">{deviceLabel(c, devices.data)}</span>
                {/if}
              </td>
              <td>
                {#if c.thread_id}
                  <a href="{resolve('/conversations')}?c={c.thread_id}">{conversationLabel(c, conversations.data)}</a>
                {:else}
                  <span class="text-label">{conversationLabel(c, conversations.data)}</span>
                {/if}
              </td>
              <td class="text-label hide-narrow">{c.transport}</td>
              <td class="text-label hide-narrow">{new Date(c.connected_at).toLocaleString()}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>
</div>

<style>
  .shell {
    padding: 16px 16px 40px;
    max-width: 1600px;
    margin: 0 auto;
  }
  .card {
    overflow: hidden;
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
  .client {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-right: 8px;
    font-weight: 500;
  }
  .pad {
    padding: 24px;
  }
</style>
