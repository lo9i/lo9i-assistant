<script lang="ts">
  import MessageSquare from "@lucide/svelte/icons/message-square";
  import Play from "@lucide/svelte/icons/play";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import { resolve } from "$app/paths";
  import type { ConnectedClient, Conversation, Device } from "$lib/api/types";
  import { fromHistory } from "$lib/chat/transcript";
  import { resource } from "$lib/daemon.svelte";
  import { clientLabel, deviceLabel } from "$lib/sessions";
  import Confirm from "../Confirm.svelte";
  import EmptyState from "../EmptyState.svelte";
  import Thread from "./Thread.svelte";

  type Props = {
    conversation: Conversation | null;
    // Open in this tab.
    open: boolean;
    /** Connected clients on this conversation. */
    sessions: ConnectedClient[];
    devices: Device[] | undefined;
    oncontinue: (threadId: string) => void;
    ondelete: (threadId: string) => void;
  };
  let { conversation, open, sessions, devices, oncontinue, ondelete }: Props = $props();
  let confirming = $state(false);

  // Reloads when the conversation gets new messages, which updates the conversation list.
  const messages = resource(
    (c) => (conversation ? c.conversations.messages(conversation.thread_id) : Promise.resolve([])),
    ["conversations"],
  );
  const items = $derived(fromHistory(messages.data ?? []).items);
  const counts = $derived({
    messages: items.filter((i) => i.kind === "user" || i.kind === "assistant").length,
    tools: items.filter((i) => i.kind === "tool").length,
  });

  function when(iso: string): string {
    return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }
</script>

<div class="column">
  {#if conversation}
    <section class="details surface--glass">
      <header>
        <h2 class="text-heading">{conversation.title || "Untitled"}</h2>
        {#if open}<span class="pill pill--accent">Open</span>{/if}
      </header>
      <dl>
        <dt class="micro-label">ID</dt>
        <dd class="id">{conversation.thread_id}</dd>
        <dt class="micro-label">Started</dt>
        <dd>{when(conversation.started_at)}</dd>
        <dt class="micro-label">Last message</dt>
        <dd>{when(conversation.updated_at)}</dd>
        <dt class="micro-label">Messages</dt>
        <dd>{messages.data ? counts.messages : "…"}</dd>
        <dt class="micro-label">Tool calls</dt>
        <dd>{messages.data ? counts.tools : "…"}</dd>
        <dt class="micro-label">Open in</dt>
        <dd>
          {#each sessions as s (`${s.id}-${s.connected_at}`)}
            <span class="session">
              {clientLabel(s)} ·
              {#if s.device_id}
                <a href="{resolve('/devices')}?d={s.device_id}">{deviceLabel(s, devices)}</a>
              {:else}
                {deviceLabel(s, devices)}
              {/if}
            </span>
          {:else}
            <span class="text-caption">No session</span>
          {/each}
        </dd>
      </dl>
      <div class="actions">
        <button class="btn btn--primary btn--sm" onclick={() => oncontinue(conversation.thread_id)}>
          <Play size={14} />Continue
        </button>
        <button
          class="btn btn--danger btn--sm"
          aria-label="Delete conversation"
          title="Delete conversation"
          onclick={() => (confirming = true)}
        >
          <Trash2 size={14} />
        </button>
      </div>
    </section>
    {#if confirming}
      <Confirm
        title="Delete this conversation?"
        text="Its messages and the files sent in it are deleted. What the assistant learned from it stays in memory."
        action="Delete"
        onanswer={(yes) => {
          confirming = false;
          if (yes) ondelete(conversation.thread_id);
        }}
      />
    {/if}
    <section class="messages surface--glass">
      <h3 class="micro-label">Messages</h3>
      {#if messages.error}
        <p class="error-text">{messages.error}</p>
      {:else}
        <!-- A new Thread per conversation, so each one opens at its first message. -->
        {#key conversation.thread_id}
          <Thread {items} thinking={false} name="" onsuggest={() => {}} follow={false}>
            {#snippet end()}
              <button class="btn btn--primary reply" onclick={() => oncontinue(conversation.thread_id)}>
                <Play size={14} />Continue
              </button>
            {/snippet}
          </Thread>
        {/key}
      {/if}
    </section>
  {:else}
    <section class="messages surface--glass">
      <EmptyState icon={MessageSquare} title="No conversation selected" text="Pick one from the table to read it here." />
    </section>
  {/if}
</div>

<style>
  .id {
    font-family: var(--font-mono);
    overflow-wrap: anywhere;
    user-select: all;
  }
  .session {
    display: block;
  }
  .column {
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
  }
  .details {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
  }
  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    margin: 0;
    align-items: baseline;
  }
  dd {
    margin: 0;
    text-align: right;
  }
  /* One row however narrow the card: Continue first, Delete (icon only) at the end. */
  .actions {
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }
  /* Where the user's next message would be. */
  .reply {
    align-self: flex-end;
    margin-bottom: 8px;
    border-radius: 16px;
    border-bottom-right-radius: 8px;
  }
  .messages {
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
  h3 {
    margin: 0;
    padding: 16px 16px 0;
  }
  .error-text {
    padding: 16px;
  }
</style>
