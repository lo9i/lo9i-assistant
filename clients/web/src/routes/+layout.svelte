<script lang="ts">
  import "../app.css";
  import { onMount, type Snippet } from "svelte";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { DaemonClient } from "$lib/api/client";
  import { ApiError } from "$lib/api/errors";
  import { EventHub } from "$lib/api/eventHub";
  import { HttpTransport, partClientId } from "$lib/api/transport";
  import { ChatController } from "$lib/chat/controller";
  import { OpenChats } from "$lib/chat/openChats";
  import { savedOpen, savedThread } from "$lib/chat/tabThread";
  import type { Daemon } from "$lib/daemon.svelte";
  import { describe, NoticeBoard } from "$lib/notices";
  import { theme } from "$lib/theme.svelte";
  import AppShell from "$lib/ui/AppShell.svelte";
  import PairPage from "$lib/ui/PairPage.svelte";

  // How this client's messages are labeled in the turn header and to other clients.
  const CHANNEL = "web";

  let { children }: { children: Snippet } = $props();
  // Where a sign-in comes back (routes/oauth): it finishes on its own, maybe in a browser that
  // isn't paired, so it gets no app around it.
  const standalone = page.url.pathname === resolve("/oauth");

  const client = new DaemonClient(new HttpTransport());
  // The voice button and each conversation open beside the first talk under ids the daemon ties to this client.
  const partClient = (part: string) => new DaemonClient(new HttpTransport(partClientId(client.clientId, part)));
  const voiceClient = partClient("voice");
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
    if (standalone) return;
    void start();
    return () => {
      closed = true;
      stop.abort();
      close();
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
      close();
      daemon = null;
      unpaired = true;
      return;
    }
    if (daemon) notices.report(e);
    else error = describe(e);
  }

  async function open(): Promise<void> {
    try {
      const { threads, active } = savedOpen();
      const [chats, voice] = await Promise.all([
        OpenChats.open((part) => (part === null ? client : partClient(part)), CHANNEL, threads, active, notices),
        ChatController.open(voiceClient, CHANNEL, savedThread("voice"), notices),
      ]);
      if (closed) {
        chats.closeAll();
        return voice.close();
      }
      daemon = { client, hub, notices, chats, voice };
    } catch (e) {
      lostPairing(e);
    }
  }

  function close(): void {
    daemon?.chats.closeAll();
    daemon?.voice.close();
  }
</script>

{#if standalone}
  {@render children()}
{:else if unpaired}
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
