<script lang="ts">
  import type { Device, PairingCode } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import Confirm from "../Confirm.svelte";
  import SettingsCard from "../Card.svelte";

  const { client } = useDaemon();
  const devices = resource((c) => c.devices.list(), ["devices"]);
  const me = resource((c) => c.auth.me(), []);
  let code = $state<PairingCode | null>(null);
  let revoking = $state<Device | null>(null);
  let error = $state("");

  async function act(action: () => Promise<unknown>): Promise<void> {
    try {
      await action();
      error = "";
    } catch (e) {
      error = describe(e);
    }
    devices.reload();
  }

  function when(iso: string): string {
    return new Date(iso).toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  async function revoke(device: Device): Promise<void> {
    await act(() => client.devices.revoke(device.id));
    // Revoking this browser logs it out; the layout shows the pairing page.
    if (device.id === me.data?.device?.id) location.reload();
  }
</script>

<SettingsCard id="devices" title="Devices" sub="Browsers allowed to use the assistant over the network. Each one paired with a one-time code.">
  {#if code}
    <div class="pairing">
      <p>On the other device, open this page's address and enter this code:</p>
      <code class="code">{code.code}</code>
      <p class="text-caption">It works once, until {when(code.expires_at)}.</p>
    </div>
  {/if}
  <div class="row">
    <button class="btn btn--primary" onclick={() => act(async () => (code = await client.devices.openPairing()))}>Pair a browser</button>
  </div>
  {#if devices.data === undefined}
    <p class="text-meta">{devices.error ?? "Loading…"}</p>
  {:else}
    <ul>
      {#each devices.data as d (d.id)}
        <li>
          <div>
            <span class="text-label">{d.name}</span>
            {#if d.id === me.data?.device?.id}<span class="pill pill--accent">This browser</span>{/if}
            <p class="text-caption">Last used {when(d.last_used_at)} from {d.last_ip || "an unknown address"} · paired {when(d.created_at)}</p>
          </div>
          <button class="btn btn--danger" onclick={() => (revoking = d)}>{d.id === me.data?.device?.id ? "Log out" : "Revoke"}</button>
        </li>
      {:else}
        <li class="text-meta">No devices paired yet.</li>
      {/each}
    </ul>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SettingsCard>

{#if revoking}
  {@const device = revoking}
  <Confirm
    title="Revoke {device.name}?"
    text="It will need a new code to use the assistant again."
    action="Revoke"
    onanswer={(yes) => {
      revoking = null;
      if (yes) void revoke(device);
    }}
  />
{/if}

<style>
  .row {
    display: flex;
    gap: 8px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
  }
  li p {
    margin: 4px 0 0;
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
