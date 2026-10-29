<script lang="ts">
  import { updated } from "$app/state";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import Power from "@lucide/svelte/icons/power";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import WifiOff from "@lucide/svelte/icons/wifi-off";
  import { DaemonUnavailableError } from "$lib/api/errors";
  import { external, useDaemon } from "$lib/daemon.svelte";
  import { answerable, coming as comingOf, comingText, type Coming } from "$lib/shutdown";

  // Says, on every page, what the daemon is up to when the page can't simply go on: a restart or stop coming (an
  // `ending` event, whoever asked for it), the daemon away while its event stream is lost (a restart, a computer
  // that slept), and a new version of this page (an update installed, the web app built again: the build this tab
  // runs is no longer the one the daemon serves). The pages load again by themselves when the stream opens again.
  let { name }: { name: string } = $props();
  const { client, hub, notices } = useDaemon();
  const connection = external(hub.subscribeConnection, hub.getConnection);
  let coming = $state<Coming | null>(null);
  let newVersion = $state(false);

  $effect(() => {
    void pending();
    return hub.on(["ending"], (data) => (coming = comingOf(data)));
  });
  // How many runs it still waits for; once none, it's going ahead and what's coming stays.
  $effect(() => hub.on(["run_finished"], () => void (coming && pending())));

  /** A restart or stop asked for before this page loaded, or the runs it waits for now. */
  async function pending(): Promise<void> {
    try {
      const found = comingOf(await client.system.ending());
      if (found) coming = found;
    } catch (e) {
      // Unreachable: the banner says so already, and this is read again when the stream opens.
      if (!(e instanceof DaemonUnavailableError)) notices.report(e);
    }
  }
  // While it waits: Cancel keeps the daemon running (not for an installed update), Now cancels the runs so it goes
  // ahead.
  let answering = $state(false);
  async function answer(act: () => Promise<unknown>, after: () => void): Promise<void> {
    answering = true;
    try {
      await act();
      after();
    } catch (e) {
      notices.report(e);
      void pending();
    } finally {
      answering = false;
    }
  }
  const takeBack = () =>
    answer(
      () => client.system.takeBackEnding(),
      () => (coming = null),
    );
  const now = () =>
    answer(
      () => client.system.endNow(),
      () => {},
    );

  // Asks for the build's version.json, which a new build replaces: no polling, once per reconnection (an update
  // restarts the daemon) and when the daemon says the web app was built again (`web_build`).
  function checkVersion(): void {
    void updated.check().then((changed) => (newVersion = changed));
  }
  $effect(() => hub.on(["web_build"], checkVersion));
  $effect(() =>
    hub.onReconnect(() => {
      coming = null;
      void pending();
      checkVersion();
    }),
  );
</script>

{#if connection.current === "lost"}
  <div class="banner surface--glass" role="status" aria-live="polite">
    {#if coming?.ending === "stop"}
      <Power size={16} />
      <span><strong>{name} was stopped.</strong> Start it again on the computer it runs on; this page reconnects then.</span>
    {:else if coming}
      <RefreshCw size={16} />
      <span><strong>{name} is restarting.</strong> Reconnecting…</span>
    {:else}
      <WifiOff size={16} />
      <span><strong>Can't reach {name} right now.</strong> It may be restarting. Reconnecting…</span>
    {/if}
    <span class="spin"><LoaderCircle size={16} /></span>
  </div>
{:else if coming}
  <div class="banner surface--glass" role="status" aria-live="polite">
    <RefreshCw size={16} />
    <span>{comingText(name, coming)}</span>
    {#if answerable(coming).cancel}
      <button class="btn btn--sm btn--ghost" onclick={takeBack} disabled={answering}>Cancel</button>
    {/if}
    {#if answerable(coming).now}
      <button class="btn btn--sm btn--danger" onclick={now} disabled={answering}>Now</button>
    {/if}
  </div>
{:else if newVersion}
  <div class="banner surface--glass fresh" role="status" aria-live="polite">
    <RefreshCw size={16} />
    <span><strong>A new version of {name} is ready.</strong> Reload to use it.</span>
    <button class="btn btn--sm btn--primary" onclick={() => location.reload()}>Reload</button>
  </div>
{/if}

<style>
  .banner {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    z-index: var(--z-popover);
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: calc(100vw - 32px);
    padding: 10px 16px;
    border-color: color-mix(in srgb, var(--color-warn) 45%, var(--surface-glass-border));
    color: var(--color-warn);
    font-size: var(--font-size-sm);
    animation: drop 0.18s ease;
  }
  .fresh {
    border-color: color-mix(in srgb, var(--color-accent) 45%, var(--surface-glass-border));
    color: var(--color-accent);
  }
  strong {
    font-weight: 600;
  }
  span {
    color: var(--color-text-primary);
  }
  .spin {
    display: inline-flex;
    color: var(--color-warn);
    animation: spin 0.9s linear infinite;
  }
  @keyframes drop {
    from {
      transform: translate(-50%, 8px);
      opacity: 0;
    }
  }
</style>
