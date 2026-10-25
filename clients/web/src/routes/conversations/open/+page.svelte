<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import List from "@lucide/svelte/icons/list";
  import Plus from "@lucide/svelte/icons/plus";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import ChatPanel from "$lib/ui/chat/ChatPanel.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { chats } = useDaemon();
  // The conversation shown; the others open beside it are in the sidebar, every one in Chat's list.
  const snapshot = external(chats.subscribe, () => chats.current.getSnapshot());
  const inInbox = $derived(snapshot.current.threadId === snapshot.current.inboxId);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const title = $derived(
    inInbox ? "Inbox" : conversations.data?.find((c) => c.thread_id === snapshot.current.threadId)?.title || "New conversation",
  );

  async function startNew(): Promise<void> {
    await chats.startNew();
  }
</script>

<TopBar {title}>
  {#snippet actions()}
    <button class="btn btn--ghost" title="Every conversation, newest first" onclick={() => goto(resolve("/conversations"))}
      ><List size={16} /><span class="hide-narrow">All conversations</span></button
    >
    <button class="btn btn--primary" onclick={startNew}><Plus size={16} /><span class="hide-narrow">New conversation</span></button>
  {/snippet}
</TopBar>

<div class="screen"><ChatPanel /></div>

<style>
  .screen {
    padding: 0 16px 8px;
    height: calc(100dvh - var(--top-bar-height));
    max-width: 1600px;
    margin: 0 auto;
  }
  @media (max-width: 680px) {
    .screen {
      padding: 0 8px 8px;
    }
  }
</style>
