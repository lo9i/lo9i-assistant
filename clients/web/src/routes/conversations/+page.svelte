<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import Plus from "@lucide/svelte/icons/plus";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import ConversationPreview from "$lib/ui/chat/ConversationPreview.svelte";
  import ConversationsTable from "$lib/ui/chat/ConversationsTable.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { chat, client, notices } = useDaemon();
  const current = external(chat.subscribe, () => chat.getSnapshot().threadId);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const clients = resource((c) => c.clients.list(), ["clients"]);
  const devices = resource((c) => c.devices.list(), ["devices"]);
  // Links from other pages (Active sessions) pick a conversation with ?c=<thread id>.
  let picked = $state<string | null>(page.url.searchParams.get("c"));

  // Until one is picked: this tab's conversation, or the most recent one.
  const selected = $derived.by(() => {
    const list = conversations.data ?? [];
    const known = (id: string | null) => id !== null && list.some((c) => c.thread_id === id);
    if (known(picked)) return picked;
    if (known(current.current)) return current.current;
    return [...list].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0]?.thread_id ?? null;
  });
  const conversation = $derived(conversations.data?.find((c) => c.thread_id === selected) ?? null);
  const sessions = $derived((clients.data ?? []).filter((c) => c.thread_id && c.thread_id === selected));

  async function continueWith(threadId: string): Promise<void> {
    await chat.resume(threadId);
    await goto(resolve("/conversations/open"));
  }

  // The one this tab is on can't be deleted while it's on it: the tab moves to a new one first.
  async function remove(threadId: string): Promise<void> {
    const list = conversations.data ?? [];
    const next = list[list.findIndex((c) => c.thread_id === threadId) + 1] ?? list.find((c) => c.thread_id !== threadId);
    try {
      if (threadId === current.current) await chat.startNew();
      await client.conversations.delete(threadId);
      picked = next?.thread_id ?? null;
    } catch (e) {
      notices.report(e);
    }
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
    oncontinue={continueWith}
  />
  <ConversationPreview
    {conversation}
    current={selected === current.current}
    {sessions}
    devices={devices.data}
    oncontinue={continueWith}
    ondelete={remove}
  />
</div>

<style>
  .screen {
    display: flex;
    /* The table takes the height of its rows, up to the screen; the preview keeps the full height. */
    align-items: flex-start;
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
    max-height: 100%;
  }
  .screen > :global(:last-child) {
    flex: 1 1 0;
    align-self: stretch;
    min-width: 0;
  }
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
      align-items: stretch;
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
