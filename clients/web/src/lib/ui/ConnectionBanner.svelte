<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import WifiOff from "@lucide/svelte/icons/wifi-off";
  import { external, useDaemon } from "$lib/daemon.svelte";

  // Says, on every page, that the daemon can't be reached while its event stream is lost (a restart, a computer
  // that slept). It goes away by itself when the stream opens again, and the pages load again then.
  let { name }: { name: string } = $props();
  const { hub } = useDaemon();
  const connection = external(hub.subscribeConnection, hub.getConnection);
</script>

{#if connection.current === "lost"}
  <div class="banner surface--glass" role="status" aria-live="polite">
    <WifiOff size={16} />
    <span><strong>Can't reach {name} right now.</strong> It may be restarting. Reconnecting…</span>
    <span class="spin"><LoaderCircle size={16} /></span>
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
