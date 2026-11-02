<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import KeyRound from "@lucide/svelte/icons/key-round";
  import Laptop from "@lucide/svelte/icons/laptop";
  import Link from "@lucide/svelte/icons/link";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import type { Device, PairingCode, Passkey } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { formatDate, t } from "$lib/i18n.svelte";
  import { addPasskey, forgetPasskey, passkeysWork, Prepared } from "$lib/passkeys";
  import Confirm from "$lib/ui/Confirm.svelte";
  import { clientLabel, conversationLabel } from "$lib/sessions";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { client, notices } = useDaemon();
  const devices = resource((c) => c.devices.list(), ["devices"]);
  // A passkey changing publishes `devices` too: they show with their device.
  const passkeys = resource((c) => c.passkeys.list(), ["devices"]);
  const me = resource((c) => c.auth.me(), []);
  const clients = resource((c) => c.clients.list(), ["clients"]);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  // Links from other pages (Active sessions, Conversations) pick a device with ?d=<device id>.
  let picked = $state<string | null>(page.url.searchParams.get("d"));
  let code = $state<PairingCode | null>(null);
  let revoking = $state<Device | null>(null);
  let removing = $state<Passkey | null>(null);
  let adding = $state(false);
  const prepared = new Prepared(() => client.passkeys.options());
  const canAdd = passkeysWork();
  // Until one is picked: this browser, or the first one.
  const device = $derived(devices.data?.find((d) => d.id === picked) ?? devices.data?.find((d) => isMe(d)) ?? devices.data?.[0]);

  const devicePasskeys = $derived(passkeysOf(device));
  const sessions = $derived((clients.data ?? []).filter((c) => c.device_id && c.device_id === device?.id));

  function sessionCount(d: Device): number {
    return (clients.data ?? []).filter((c) => c.device_id === d.id).length;
  }

  function passkeysOf(d: Device | undefined): Passkey[] {
    return (passkeys.data ?? []).filter((p) => p.device_id === d?.id);
  }

  function isMe(d: Device): boolean {
    return d.id === me.data?.device?.id;
  }

  function when(iso: string): string {
    return formatDate(iso, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  async function pair(): Promise<void> {
    try {
      code = await client.devices.openPairing();
    } catch (e) {
      notices.report(e);
    }
  }

  // Asked for once this browser is known to be a device, so Add a passkey asks the browser at once.
  $effect(() => {
    if (canAdd && me.data?.device) prepared.prepare();
  });

  // The sidebar's + links here with ?pair: open a code, then drop the parameter so a reload doesn't open another.
  $effect(() => {
    if (!page.url.searchParams.has("pair")) return;
    void pair();
    void goto(resolve("/devices"), { replaceState: true });
  });

  async function addHere(): Promise<void> {
    adding = true;
    try {
      if (await addPasskey(client.passkeys, prepared)) notices.notify(t("devices.passkeyAdded"));
    } catch (e) {
      notices.report(e);
    }
    adding = false;
  }

  async function removePasskey(p: Passkey): Promise<void> {
    try {
      await client.passkeys.remove(p.id);
    } catch (e) {
      return notices.report(e);
    }
    forgetPasskey(p);
  }

  async function revoke(d: Device): Promise<void> {
    const its = passkeysOf(d);
    try {
      await client.devices.revoke(d.id);
    } catch (e) {
      return notices.report(e);
    }
    its.forEach(forgetPasskey);
    // Revoking this browser logs it out; the layout shows the pairing page.
    if (isMe(d)) location.reload();
  }
</script>

<TopBar title={t("nav.devices")}>
  {#snippet actions()}
    <button class="btn btn--primary" onclick={pair}><Link size={16} /><span class="hide-narrow">{t("nav.pairBrowser")}</span></button>
  {/snippet}
</TopBar>

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">{t("devices.title")}</h2>
        <p class="text-meta">{t("devices.hint")}</p>
      </div>
      {#if devices.data}<span class="pill">{devices.data.length}</span>{/if}
    </header>
    <div class="scroll">
      {#if devices.error}
        <p class="error-text pad">{devices.error}</p>
      {:else if devices.data?.length === 0}
        <EmptyState icon={Laptop} title={t("devices.none")} text={t("devices.noneHint")} />
      {:else if devices.data && device}
        <table class="data-table">
          <thead>
            <tr>
              <th>{t("devices.browserColumn")}</th>
              <th>{t("devices.sessions")}</th>
              <th>{t("devices.lastUsed")}</th>
              <th class="hide-narrow">{t("devices.passkeys")}</th>
              <th class="hide-narrow">{t("devices.from")}</th>
              <th class="hide-narrow">{t("devices.paired")}</th>
            </tr>
          </thead>
          <tbody>
            {#each devices.data as d (d.id)}
              <tr class:selected={d.id === device.id} onclick={() => (picked = d.id)}>
                <td>
                  <button class="row-button" onclick={() => (picked = d.id)}>{d.name}</button>
                  {#if isMe(d)}<span class="pill pill--accent">{t("devices.thisBrowser")}</span>{/if}
                </td>
                <td class="text-label">{sessionCount(d) || "—"}</td>
                <td class="text-label">{when(d.last_used_at)}</td>
                <td class="text-label hide-narrow">{passkeysOf(d).length || "—"}</td>
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
          <h2 class="text-heading">{t("devices.code")}</h2>
          <button class="btn btn--ghost btn--sm" onclick={() => (code = null)}>{t("secret.hide")}</button>
        </header>
        <p>{t("devices.codeHint")}</p>
        <code class="code">{code.code}</code>
        <p class="text-caption">{t("devices.codeOnce", { until: when(code.expires_at) })}</p>
      </section>
    {/if}
    {#if device}
      <section class="details surface--glass">
        <header>
          <h2 class="text-heading">{device.name}</h2>
          {#if isMe(device)}<span class="pill pill--accent">{t("devices.thisBrowser")}</span>{/if}
        </header>
        <dl>
          <dt class="micro-label">{t("devices.lastUsed")}</dt>
          <dd>{when(device.last_used_at)}</dd>
          <dt class="micro-label">{t("devices.from")}</dt>
          <dd>{device.last_ip || t("devices.unknownAddress")}</dd>
          <dt class="micro-label">{t("devices.paired")}</dt>
          <dd>{when(device.created_at)}</dd>
        </dl>
        <div class="sessions">
          <h3 class="micro-label">{t("devices.openSessions")}</h3>
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
            <p class="text-caption">{t("devices.noneNow")}</p>
          {/each}
        </div>
        <div class="passkeys">
          <h3 class="micro-label">{t("devices.passkeys")}</h3>
          {#each devicePasskeys as p (p.id)}
            <div class="passkey">
              <p>
                {t("devices.passkeyAddedOn", { when: when(p.created_at) })}
                <span class="text-caption">· {t("devices.passkeyUsed", { when: when(p.last_used_at) })}</span>
                {#if p.synced}<span class="pill" title={t("devices.syncedHint")}>{t("devices.synced")}</span>{/if}
              </p>
              <button
                class="btn btn--ghost btn--sm"
                aria-label={t("devices.removePasskey")}
                title={t("devices.removePasskey")}
                onclick={() => (removing = p)}><Trash2 size={14} /></button
              >
            </div>
          {:else}
            <p class="text-caption">{isMe(device) && canAdd ? t("devices.noPasskeysHere") : t("devices.noPasskeys")}</p>
          {/each}
          {#if isMe(device)}
            {#if canAdd}
              <button class="btn btn--outline btn--sm add-passkey" onclick={addHere} disabled={adding}>
                <KeyRound size={14} />{t("devices.addPasskey")}
              </button>
            {:else}
              <p class="text-caption">{t("devices.passkeysNeedHttps")}</p>
            {/if}
          {/if}
        </div>
        <button class="btn btn--danger btn--sm revoke" onclick={() => (revoking = device)}>
          {isMe(device) ? t("devices.logOut") : t("devices.revoke")}
        </button>
      </section>
    {:else if !code}
      <section class="details surface--glass">
        <EmptyState icon={KeyRound} title={t("devices.noneSelected")} text={t("devices.noneSelectedHint")} />
      </section>
    {/if}
  </div>
</div>

{#if removing}
  {@const p = removing}
  <Confirm
    title={t("devices.removePasskeyTitle")}
    text={t("devices.removePasskeyText")}
    action={t("devices.removePasskey")}
    onanswer={(yes) => {
      removing = null;
      if (yes) void removePasskey(p);
    }}
  />
{/if}

{#if revoking}
  {@const d = revoking}
  <Confirm
    title={isMe(d) ? t("devices.logOutTitle") : t("devices.revokeTitle", { name: d.name })}
    text={t("devices.revokeText")}
    action={isMe(d) ? t("devices.logOut") : t("devices.revoke")}
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
    padding: 0 16px 8px;
    height: calc(100dvh - var(--top-bar-height));
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
  .passkeys {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .passkeys h3 {
    margin: 0 0 2px;
  }
  .passkey {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .passkey .pill {
    margin-left: 6px;
  }
  .add-passkey {
    align-self: flex-start;
    margin-top: 4px;
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
