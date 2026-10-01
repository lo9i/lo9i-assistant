<script lang="ts">
  import MessageSquare from "@lucide/svelte/icons/message-square";
  import Play from "@lucide/svelte/icons/play";
  import type { Conversation } from "$lib/api/types";
  import { fromHistory } from "$lib/chat/transcript";
  import { resource } from "$lib/daemon.svelte";
  import EmptyState from "../EmptyState.svelte";
  import Thread from "./Thread.svelte";

  type Props = { conversation: Conversation | null; current: boolean; oncontinue: (threadId: string) => void };
  let { conversation, current, oncontinue }: Props = $props();

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
        {#if current}<span class="pill pill--accent">This tab</span>{/if}
      </header>
      <dl>
        <dt class="micro-label">Started</dt>
        <dd>{when(conversation.started_at)}</dd>
        <dt class="micro-label">Last message</dt>
        <dd>{when(conversation.updated_at)}</dd>
        <dt class="micro-label">Messages</dt>
        <dd>{messages.data ? counts.messages : "…"}</dd>
        <dt class="micro-label">Tool calls</dt>
        <dd>{messages.data ? counts.tools : "…"}</dd>
      </dl>
      <button class="btn btn--primary btn--sm continue" onclick={() => oncontinue(conversation.thread_id)}>
        <Play size={14} />Continue
      </button>
    </section>
    <section class="messages surface--glass">
      <h3 class="micro-label">Messages</h3>
      {#if messages.error}
        <p class="error-text">{messages.error}</p>
      {:else}
        <Thread {items} thinking={false} name="" onsuggest={() => {}}>
          {#snippet end()}
            <button class="btn btn--primary reply" onclick={() => oncontinue(conversation.thread_id)}>
              <Play size={14} />Continue
            </button>
          {/snippet}
        </Thread>
      {/if}
    </section>
  {:else}
    <section class="messages surface--glass">
      <EmptyState icon={MessageSquare} title="No conversation selected" text="Pick one from the table to read it here." />
    </section>
  {/if}
</div>

<style>
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
  .continue {
    align-self: flex-start;
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
