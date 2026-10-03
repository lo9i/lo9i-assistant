<script lang="ts">
  import "../app.css";
  import { onMount, type Snippet } from "svelte";
  import { DaemonClient } from "$lib/api/client";
  import { ApiError } from "$lib/api/errors";
  import { EventHub } from "$lib/api/eventHub";
  import { HttpTransport } from "$lib/api/transport";
  import { ChatController } from "$lib/chat/controller";
  import { savedThread } from "$lib/chat/tabThread";
  import type { Daemon } from "$lib/daemon.svelte";
  import { describe, NoticeBoard } from "$lib/notices";
  import { theme } from "$lib/theme.svelte";
  import AppShell from "$lib/ui/AppShell.svelte";
  import PairPage from "$lib/ui/PairPage.svelte";

  // How this client's messages are labeled in the turn header and to other clients.
  const CHANNEL = "web";

  let { children }: { children: Snippet } = $props();

  const client = new DaemonClient(new HttpTransport());
  const hub = new EventHub();
  const notices = new NoticeBoard();
  let daemon = $state<Daemon | null>(null);
  let error = $state<string | null>(null);
  // Every request needs a paired device; until this browser is one, the pairing page shows.
  let unpaired = $state(false);
  const stop = new AbortController();
  let closed = false;
  let listening = false;

  onMount(() => theme.apply());

  onMount(() => {
    void start();
    return () => {
      closed = true;
      stop.abort();
      daemon?.chat.close();
    };
  });

  async function start(): Promise<void> {
    error = null;
    if (!(await paired())) return;
    if (!listening) {
      listening = true;
      hub.listen(client, stop.signal).catch(lostPairing);
    }
    await open();
  }

  async function paired(): Promise<boolean> {
    try {
      await client.auth.me();
      return true;
    } catch (e) {
      lostPairing(e);
      return false;
    }
  }

  /** A device revoked while the page is open ends up back on the pairing page. */
  function lostPairing(e: unknown): void {
    if (e instanceof ApiError && e.status === 401) {
      daemon?.chat.close();
      daemon = null;
      unpaired = true;
      return;
    }
    if (daemon) notices.report(e);
    else error = describe(e);
  }

  async function open(): Promise<void> {
    try {
      const chat = await ChatController.open(client, CHANNEL, savedThread(), notices);
      if (closed) return chat.close();
      daemon = { client, hub, notices, chat };
    } catch (e) {
      lostPairing(e);
    }
  }
</script>

{#if unpaired}
  <PairPage {client} />
{:else if daemon}
  <AppShell {daemon}>{@render children()}</AppShell>
{:else}
  <div class="splash">
    {#if error}
      <p>{error}</p>
      <button class="btn btn--neutral" onclick={() => start()}>Try again</button>
    {:else}
      <div class="spinner"></div>
    {/if}
  </div>
{/if}

<style>
  .splash {
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 16px;
    min-height: 100vh;
    color: var(--color-text-muted);
  }
</style>
