<script lang="ts">
  import type { Snippet } from "svelte";
  import type { Failing, JobFinished } from "$lib/api/types";
  import { followRuns } from "$lib/chat/events";
  import { saveThread } from "$lib/chat/tabThread";
  import { external, provideDaemon, resource, type Daemon } from "$lib/daemon.svelte";
  import { failingNotice } from "$lib/health";
  import { sidebar } from "$lib/sidebar.svelte";
  import Sidebar from "./Sidebar.svelte";
  import Toasts from "./Toasts.svelte";
  import VoiceButton from "./voice/VoiceButton.svelte";

  let { daemon, children }: { daemon: Daemon; children: Snippet } = $props();

  // The layout creates the daemon once and never replaces it.
  // svelte-ignore state_referenced_locally
  provideDaemon(daemon);
  // svelte-ignore state_referenced_locally
  const { chat, voice, hub, notices } = daemon;
  const name = resource((client) => client.identity.name(), ["settings"]);
  const threadId = external(chat.subscribe, () => chat.getSnapshot().threadId);
  const voiceThreadId = external(voice.subscribe, () => voice.getSnapshot().threadId);

  // The chat follows runs whichever page is open, so a reply keeps streaming in the background.
  $effect(() => followRuns(hub, chat));
  $effect(() => followRuns(hub, voice));
  $effect(() => saveThread(threadId.current));
  $effect(() => saveThread(voiceThreadId.current, "voice"));
  $effect(() => {
    document.title = name.data || "lo9i";
  });
  $effect(() =>
    hub.on(["job"], (data) => {
      const job = data as JobFinished;
      notices.notify(`Job ${job.name}: ${job.status}`, job.status === "ok" ? "info" : "warning");
    }),
  );
  $effect(() => hub.on(["failing"], (data) => notices.notify(failingNotice(data as Failing), "warning")));

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
</div>
<VoiceButton />
<Toasts {notices} />

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
  @media (max-width: 680px) {
    .app-layout {
      --sidebar-rail: 64px;
    }
  }
</style>
