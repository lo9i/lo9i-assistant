<script lang="ts">
  import "../app.css";
  import { onMount, type Snippet } from "svelte";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { DaemonClient } from "$lib/api/client";
  import { ApiError, DaemonUnavailableError } from "$lib/api/errors";
  import { EventHub } from "$lib/api/eventHub";
  import { HttpTransport, partClientId } from "$lib/api/transport";
  import { ChatController } from "$lib/chat/controller";
  import { followRuns } from "$lib/chat/events";
  import { OpenChats } from "$lib/chat/openChats";
  import { ChatTab } from "$lib/chat/tab";
  import { savedOpen, savedThread } from "$lib/chat/tabThread";
  import type { Daemon } from "$lib/daemon.svelte";
  import { describe, NoticeBoard } from "$lib/notices";
  import { language, t } from "$lib/i18n.svelte";
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
  // The voice and text buttons and each conversation open beside the first talk under ids the daemon ties to
  // this client.
  const partClient = (part: string) =>
    new DaemonClient(new HttpTransport(partClientId(client.clientId, part)), client.following, client.followingLogs);
  const voiceClient = partClient("voice");
  const textClient = partClient("text");
  const hub = new EventHub();
  const notices = new NoticeBoard();
  // Every chat of the tab, the quick buttons' too: each hears of runs from the moment it's made, before its history
  // has loaded, so a run that starts meanwhile shows. Each try at opening makes its own, so a chat that finishes
  // opening after a try failed hears nothing.
  let tab = new ChatTab();
  let daemon = $state<Daemon | null>(null);
  let error = $state<string | null>(null);
  // Every request needs a paired device; until this browser is one, the pairing page shows.
  let unpaired = $state(false);
  const stop = new AbortController();
  let closed = false;
  let listening = false;
  // Before the app opens, a daemon that can't be reached (restarting, not started yet) is tried again this often,
  // as the event stream does once it's open.
  const RETRY_MS = 2000;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let retrying = $state(false);

  onMount(() => theme.apply());
  onMount(() => language.use(language.choice));

  onMount(() => {
    if (standalone) return;
    const unfollow = followRuns(hub, { all: () => tab.all() });
    void start();
    return () => {
      closed = true;
      unfollow();
      clearTimeout(retry);
      stop.abort();
      close();
    };
  });

  async function start(): Promise<void> {
    clearTimeout(retry);
    error = null;
    retrying = false;
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
    else unreachable(e);
  }

  function unreachable(e: unknown): void {
    error = describe(e);
    retrying = e instanceof DaemonUnavailableError && !closed;
    if (retrying) retry = setTimeout(() => void start(), RETRY_MS);
  }

  async function open(): Promise<void> {
    tab = new ChatTab();
    try {
      const { threads, active } = savedOpen();
      // The chats first: a run waiting for an answer in a conversation one of them is on asks there, not behind a
      // quick button (ChatTab.asks).
      const chats = await OpenChats.open((part) => (part === null ? client : partClient(part)), CHANNEL, threads, active, notices, tab);
      const [voice, text] = await Promise.all([
        ChatController.open(voiceClient, CHANNEL, savedThread("voice"), notices, tab, "quick"),
        ChatController.open(textClient, CHANNEL, savedThread("text"), notices, tab, "quick"),
      ]);
      if (closed) {
        chats.closeAll();
        voice.close();
        return text.close();
      }
      daemon = { client, hub, notices, chats, voice, text };
    } catch (e) {
      tab.all().forEach((chat) => chat.close());
      lostPairing(e);
    }
  }

  function close(): void {
    daemon?.chats.closeAll();
    daemon?.voice.close();
    daemon?.text.close();
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
      {#if retrying}
        <p class="text-meta trying"><span class="spinner"></span>{t("app.tryingAgain")}</p>
      {:else}
        <button class="btn btn--neutral" onclick={() => start()}>{t("app.tryAgain")}</button>
      {/if}
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
  .trying {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0;
  }
</style>
