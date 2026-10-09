<script lang="ts">
  import GitBranchPlus from "@lucide/svelte/icons/git-branch-plus";
  import House from "@lucide/svelte/icons/house";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import ChatPanel from "$lib/ui/chat/ChatPanel.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { chat } = useDaemon();
  // One conversation, home; a side conversation is a branch off it for focused work, left with Back home.
  const snapshot = external(chat.subscribe, () => chat.getSnapshot());
  const onSide = $derived(snapshot.current.threadId !== snapshot.current.homeId);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const sideTitle = $derived(conversations.data?.find((c) => c.thread_id === snapshot.current.threadId)?.title || "New side conversation");
</script>

<TopBar title={onSide ? sideTitle : "Chat"}>
  {#snippet actions()}
    {#if onSide}
      <button class="btn btn--primary" onclick={() => chat.goHome()}><House size={16} /><span class="hide-narrow">Back home</span></button>
    {:else}
      <button class="btn btn--ghost" title="Focused work in a conversation of its own" onclick={() => chat.startNew()}
        ><GitBranchPlus size={16} /><span class="hide-narrow">Side conversation</span></button
      >
    {/if}
  {/snippet}
</TopBar>

<div class="screen"><ChatPanel /></div>

<style>
  .screen {
    padding: 0 16px 16px;
    height: calc(100dvh - 76px);
    max-width: 1600px;
    margin: 0 auto;
  }
  @media (max-width: 680px) {
    .screen {
      height: calc(100dvh - 60px);
      padding: 0 8px 8px;
    }
  }
</style>
