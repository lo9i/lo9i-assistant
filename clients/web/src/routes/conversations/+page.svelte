<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import Inbox from "@lucide/svelte/icons/inbox";
  import Plus from "@lucide/svelte/icons/plus";
  import { agentCommands } from "$lib/chat/commands";
  import { draft } from "$lib/chat/draft.svelte";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import Composer from "$lib/ui/chat/Composer.svelte";
  import ConversationPreview from "$lib/ui/chat/ConversationPreview.svelte";
  import ConversationsTable from "$lib/ui/chat/ConversationsTable.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  // What Chat opens to: a message box that sends to the inbox, which routes each message to the
  // conversation it's about or a new one, and every conversation, newest activity first.
  const OPEN = resolve("/conversations/open");
  const { chats, client, notices } = useDaemon();
  const open = external(chats.subscribe, chats.getSnapshot);
  const current = $derived(open.current.chats.find((c) => c.key === open.current.activeKey)?.state.threadId ?? null);
  const openThreads = $derived(open.current.chats.map((c) => c.state.threadId));
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  // The inbox has an entry of its own above the list.
  const listed = $derived(conversations.data?.filter((c) => !c.inbox));
  const agents = resource((c) => c.conversations.agents(), ["mcp"]);
  const clients = resource((c) => c.clients.list(), ["clients"]);
  const devices = resource((c) => c.devices.list(), ["devices"]);
  // Links from other pages (Active sessions, Notifications) pick a conversation with ?c=<thread id>.
  let picked = $state<string | null>(page.url.searchParams.get("c"));
  let text = $state("");
  let files = $state<File[]>([]);

  // Until one is picked: this tab's conversation, or the most recent one.
  const selected = $derived.by(() => {
    const list = listed ?? [];
    const known = (id: string | null) => id !== null && list.some((c) => c.thread_id === id);
    if (known(picked)) return picked;
    if (known(current)) return current;
    return list[0]?.thread_id ?? null;
  });
  const conversation = $derived(listed?.find((c) => c.thread_id === selected) ?? null);
  const sessions = $derived((clients.data ?? []).filter((c) => c.thread_id && c.thread_id === selected));

  async function continueWith(threadId: string): Promise<void> {
    await chats.show(threadId);
    await goto(OPEN);
  }

  /** The chat panel sends it from the inbox once it opens, so it's shown and spoken like any message. */
  async function write(message: string, attached: File[]): Promise<void> {
    draft.queue(message, attached);
    await chats.goInbox();
    await goto(OPEN);
  }

  async function openInbox(): Promise<void> {
    await chats.goInbox();
    await goto(OPEN);
  }

  // One open here can't be deleted while it's open: it's closed first, or the last one goes to the inbox.
  async function remove(threadId: string): Promise<void> {
    const list = listed ?? [];
    const next = list[list.findIndex((c) => c.thread_id === threadId) + 1] ?? list.find((c) => c.thread_id !== threadId);
    try {
      const opened = open.current.chats.find((c) => c.state.threadId === threadId);
      if (opened && open.current.chats.length > 1) await chats.close(opened.key);
      else if (opened) await chats.current.goInbox();
      await client.conversations.delete(threadId);
      picked = next?.thread_id ?? null;
    } catch (e) {
      notices.report(e);
    }
  }

  async function startNew(): Promise<void> {
    await chats.startNew();
    await goto(OPEN);
  }
</script>

<TopBar title="Chat">
  {#snippet actions()}
    <button class="btn btn--ghost" title="Quick questions, and where each message went" onclick={openInbox}
      ><Inbox size={16} /><span class="hide-narrow">Inbox</span></button
    >
    <button class="btn btn--primary" onclick={startNew}><Plus size={16} /><span class="hide-narrow">New conversation</span></button>
  {/snippet}
</TopBar>

<div class="screen">
  <section class="write surface--glass" aria-label="Write a message">
    <p class="text-meta">
      Write anything: it goes on in the conversation it's about, or starts a new one. Quick questions are answered in the inbox.
    </p>
    <Composer
      bind:text
      bind:files
      busy={false}
      running={false}
      onsend={write}
      onstop={() => {}}
      oncommand={(name, arg) => write(`${name} ${arg}`.trim(), [])}
      extra={agentCommands(agents.data ?? [])}
    />
  </section>
  <div class="lists">
    <ConversationsTable
      conversations={listed}
      error={conversations.error}
      {selected}
      open={openThreads}
      onselect={(id) => (picked = id)}
      oncontinue={continueWith}
    />
    <ConversationPreview
      {conversation}
      open={selected !== null && openThreads.includes(selected)}
      {sessions}
      devices={devices.data}
      oncontinue={continueWith}
      ondelete={remove}
    />
  </div>
</div>

<style>
  .screen {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 0 16px 16px;
    height: calc(100dvh - 76px);
    max-width: 1600px;
    margin: 0 auto;
  }
  .write {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px 16px;
  }
  .write p {
    margin: 0;
  }
  .lists {
    flex: 1;
    min-height: 0;
    display: flex;
    /* The table takes the height of its rows, up to the screen; the preview keeps the full height. */
    align-items: flex-start;
    gap: 16px;
  }
  /* The table takes three quarters of the width, the preview the rest. */
  .lists > :global(:first-child) {
    flex: 3 1 0;
    min-width: 0;
    max-height: 100%;
  }
  .lists > :global(:last-child) {
    flex: 1 1 0;
    align-self: stretch;
    min-width: 0;
  }
  @media (max-width: 900px) {
    .lists {
      flex-direction: column;
      align-items: stretch;
    }
  }
  @media (max-width: 680px) {
    .screen {
      height: calc(100dvh - 60px);
      padding: 0 8px 8px;
      gap: 8px;
    }
  }
</style>
