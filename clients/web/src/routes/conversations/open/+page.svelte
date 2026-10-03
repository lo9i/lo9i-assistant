<script lang="ts">
  import { resolve } from "$app/paths";
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import Plus from "@lucide/svelte/icons/plus";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import ChatPanel from "$lib/ui/chat/ChatPanel.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { chat } = useDaemon();
  const threadId = external(chat.subscribe, () => chat.getSnapshot().threadId);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const title = $derived(conversations.data?.find((c) => c.thread_id === threadId.current)?.title || "New conversation");
</script>

<TopBar {title}>
  {#snippet actions()}
    <a class="btn btn--ghost" href={resolve("/conversations")}><ArrowLeft size={16} /><span class="hide-narrow">All conversations</span></a>
    <button class="btn btn--primary" onclick={() => chat.startNew()}
      ><Plus size={16} /><span class="hide-narrow">New conversation</span></button
    >
  {/snippet}
</TopBar>

<div class="screen"><ChatPanel /></div>

<style>
  .screen {
    padding: 16px;
    height: calc(100dvh - 76px);
    max-width: 1600px;
    margin: 0 auto;
  }
  @media (max-width: 680px) {
    .screen {
      height: calc(100dvh - 60px);
      padding: 8px;
    }
  }
</style>
