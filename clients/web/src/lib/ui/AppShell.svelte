<script lang="ts">
  import TextButton from "./quick/TextButton.svelte";
  import VoiceButton from "./quick/VoiceButton.svelte";
  import type { Snippet } from "svelte";
  import type { BackgroundEnded, Failing, JobFinished, SignedOut } from "$lib/api/types";
  import { followRuns } from "$lib/chat/events";
  import { saveOpen, saveThread } from "$lib/chat/tabThread";
  import { external, provideDaemon, resource, type Daemon } from "$lib/daemon.svelte";
  import { failingNotice, signedOutNotice } from "$lib/health";
  import { openConversation } from "$lib/ui/openConversation";
  import { sidebar } from "$lib/sidebar.svelte";
  import Sidebar from "./Sidebar.svelte";
  import KeptKeysDialog from "./plugins/KeptKeysDialog.svelte";
  import Toasts from "./Toasts.svelte";

  let { daemon, children }: { daemon: Daemon; children: Snippet } = $props();

  // The channel of scheduled jobs' runs (core/context.py), whose conversations aren't opened.
  const UNATTENDED = "worker";

  // The layout creates the daemon once and never replaces it.
  // svelte-ignore state_referenced_locally
  provideDaemon(daemon);
  // svelte-ignore state_referenced_locally
  const { chats, voice, text, hub, notices } = daemon;
  const name = resource((client) => client.identity.name(), ["settings"]);
  const open = external(chats.subscribe, chats.getSnapshot);
  const voiceThreadId = external(voice.subscribe, () => voice.getSnapshot().threadId);
  const textThreadId = external(text.subscribe, () => text.getSnapshot().threadId);

  // The chat follows runs whichever page is open, so a reply keeps streaming in the background.
  $effect(() => followRuns(hub, chats));
  $effect(() => followRuns(hub, { all: () => [voice, text] }));
  $effect(() => {
    void open.current;
    saveOpen(chats.saved());
  });
  $effect(() => saveThread(voiceThreadId.current, "voice"));
  $effect(() => saveThread(textThreadId.current, "text"));
  $effect(() => {
    document.title = name.data || "lo9i";
  });
  $effect(() =>
    hub.on(["job"], (data) => {
      const job = data as JobFinished;
      notices.notify(`Job ${job.name}: ${job.status}`, job.status === "ok" ? "info" : "warning");
    }),
  );
  // Work started in a conversation opens it; a scheduled job's run is no conversation to open.
  $effect(() =>
    hub.on(["background_ended"], (data) => {
      const ended = data as BackgroundEnded;
      const open =
        ended.channel === UNATTENDED
          ? undefined
          : { label: "Open its conversation", run: () => void openConversation(chats, notices, ended.thread_id) };
      notices.notify(ended.text, ended.ok ? "info" : "warning", open);
    }),
  );
  $effect(() => hub.on(["failing"], (data) => notices.notify(failingNotice(data as Failing), "warning")));
  $effect(() => hub.on(["signed_out"], (data) => notices.notify(signedOutNotice(data as SignedOut), "warning")));

  function onKeydown(e: KeyboardEvent): void {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
      e.preventDefault();
      sidebar.toggle();
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="app-layout" class:collapsed={sidebar.collapsed}>
  <Sidebar name={name.data || "lo9i"} />
  <main class="main">{@render children()}</main>
  <!-- Floating in the window's bottom right corner, on every page: typing above, talking below. -->
  <div class="quick">
    <TextButton />
    <VoiceButton />
  </div>
</div>
<Toasts {notices} />
<KeptKeysDialog />

<style>
  .app-layout {
    --sidebar-rail: 220px;
    display: grid;
    grid-template-columns: calc(var(--sidebar-rail) + 32px) minmax(0, 1fr);
    min-height: 100vh;
    transition: grid-template-columns 0.18s ease;
  }
  .collapsed {
    --sidebar-rail: 64px;
  }
  .main {
    min-width: 0;
  }
  .quick {
    position: fixed;
    right: 24px;
    bottom: 24px;
    z-index: var(--z-popover);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  @media (max-width: 680px) {
    .app-layout {
      --sidebar-rail: 64px;
    }
  }
</style>
