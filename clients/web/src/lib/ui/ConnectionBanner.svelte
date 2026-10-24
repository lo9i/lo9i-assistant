<script lang="ts">
  import { updated } from "$app/state";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import Power from "@lucide/svelte/icons/power";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import WifiOff from "@lucide/svelte/icons/wifi-off";
  import { DaemonUnavailableError } from "$lib/api/errors";
  import { external, useDaemon } from "$lib/daemon.svelte";
  import { comingText, type Ending } from "$lib/shutdown";

  // Says, on every page, what the daemon is up to when the page can't simply go on: a restart or stop coming (an
  // `ending` event, whoever asked for it), the daemon away while its event stream is lost (a restart, a computer
  // that slept), and a new version of this page once it's back (an update installed: the build this tab runs is
  // no longer the one the daemon serves). The pages load again by themselves when the stream opens again.
  let { name }: { name: string } = $props();
  const { client, hub, notices } = useDaemon();
  const connection = external(hub.subscribeConnection, hub.getConnection);
  let coming = $state<{ ending: Ending; waiting: number } | null>(null);
  let newVersion = $state(false);

  $effect(() => {
    void pending();
    return hub.on(["ending"], (data) => {
      coming = data.taken_back ? null : { ending: data.ending as Ending, waiting: Number(data.waiting_for_runs ?? 0) };
    });
  });
  // How many runs it still waits for; once none, it's going ahead and what's coming stays.
  $effect(() => hub.on(["run_finished"], () => void (coming && pending())));

  /** A restart or stop asked for before this page loaded, or the runs it waits for now. */
  async function pending(): Promise<void> {
    try {
      const found = await client.system.ending();
      if (found.ending) coming = { ending: found.ending as Ending, waiting: found.waiting_for_runs };
    } catch (e) {
      // Unreachable: the banner says so already, and this is read again when the stream opens.
      if (!(e instanceof DaemonUnavailableError)) notices.report(e);
    }
  }
  $effect(() =>
    hub.onReconnect(() => {
      coming = null;
      void pending();
      // Asks for the build's version.json, which an update replaces: no polling, once per reconnection.
      void updated.check().then((changed) => (newVersion = changed));
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
    <span>{comingText(name, coming.ending, coming.waiting)}</span>
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
