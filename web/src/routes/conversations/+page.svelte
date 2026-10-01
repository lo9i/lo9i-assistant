<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import Plus from "@lucide/svelte/icons/plus";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import ConversationPreview from "$lib/ui/chat/ConversationPreview.svelte";
  import ConversationsTable from "$lib/ui/chat/ConversationsTable.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { chat } = useDaemon();
  const current = external(chat.subscribe, () => chat.getSnapshot().threadId);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  let picked = $state<string | null>(null);

  // Until one is picked: this tab's conversation, or the most recent one.
  const selected = $derived.by(() => {
    const list = conversations.data ?? [];
    const known = (id: string | null) => id !== null && list.some((c) => c.thread_id === id);
    if (known(picked)) return picked;
    if (known(current.current)) return current.current;
    return [...list].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0]?.thread_id ?? null;
  });
  const conversation = $derived(conversations.data?.find((c) => c.thread_id === selected) ?? null);

  async function continueWith(threadId: string): Promise<void> {
    await chat.resume(threadId);
    await goto(resolve("/conversations/open"));
  }

  async function startNew(): Promise<void> {
    await chat.startNew();
    await goto(resolve("/conversations/open"));
  }
</script>

<TopBar title="Conversations">
  {#snippet actions()}
    <button class="btn btn--primary" onclick={startNew}><Plus size={16} /><span class="hide-narrow">New conversation</span></button>
  {/snippet}
</TopBar>

<div class="screen">
  <ConversationsTable
    conversations={conversations.data}
    error={conversations.error}
    {selected}
    current={current.current}
    onselect={(id) => (picked = id)}
  />
  <ConversationPreview {conversation} current={selected === current.current} oncontinue={continueWith} />
</div>

<style>
  .screen {
    display: flex;
    gap: 16px;
    padding: 16px;
    height: calc(100dvh - 76px);
    max-width: 1600px;
    margin: 0 auto;
  }
  /* The table takes three quarters of the width, the preview the rest. */
  .screen > :global(:first-child) {
    flex: 3 1 0;
    min-width: 0;
  }
  .screen > :global(:last-child) {
    flex: 1 1 0;
    min-width: 0;
  }
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
    }
  }
  @media (max-width: 680px) {
    .screen {
      height: calc(100dvh - 60px);
      padding: 8px;
      gap: 8px;
    }
  }
</style>
