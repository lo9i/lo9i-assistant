<script lang="ts">
  import type { Conversation } from "$lib/api/types";
  import { cardStatus, lastMessages } from "$lib/chat/cards";
  import type { ChatSnapshot } from "$lib/chat/controller";
  import { glance } from "$lib/chat/glance.svelte";
  import { fromHistory } from "$lib/chat/transcript";
  import { t } from "$lib/i18n.svelte";
  import { markdown } from "$lib/markdown";
  import StatusPill from "../chat/board/StatusPill.svelte";

  type Props = {
    conversation: Conversation;
    /** This tab's chat on it, which shows it live; null when it isn't open here. */
    live: ChatSnapshot | null;
    /** A reply or a task runs in it, started from anywhere. */
    working: boolean;
    /** The assistant's name, before its message. */
    name: string;
    onopen: () => void;
  };
  let { conversation, live, working, name, onopen }: Props = $props();

  const seen = glance(() => ({
    threadId: conversation.thread_id,
    updatedAt: conversation.updated_at,
    working,
    wanted: live === null,
  }));
  const latest = $derived(lastMessages(live ? live.transcript.items : fromHistory(seen.history).items, 1)[0]);
  const status = $derived(cardStatus(live, working, seen.asking));
  const who = $derived(latest?.from === "user" ? t("board.you") : latest?.from === "agent" ? t("board.task") : name);

  /** A message's text without its Markdown, on one line. The parser loads nothing the text points to. */
  function plain(text: string): string {
    const shown = new DOMParser().parseFromString(markdown(text), "text/html").body.textContent ?? "";
    return shown.replace(/\s+/g, " ").trim();
  }
</script>

<li>
  <button class="row" onclick={onopen} title={t("board.openFull")}>
    <span class="head">
      <span class="title">{conversation.title || t("nav.newConversation")}</span>
      <StatusPill {status} />
    </span>
    {#if seen.error}
      <span class="error-text latest">{seen.error}</span>
    {:else if latest}
      <span class="text-label latest"><strong>{who}:</strong> {plain(latest.text)}</span>
    {/if}
  </button>
</li>

<style>
  li {
    border-top: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  li:first-child {
    border-top: 0;
  }
  .row {
    display: flex;
    flex-direction: column;
    gap: 3px;
    width: 100%;
    padding: 8px 6px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .row:hover,
  .row:focus-visible {
    background: var(--color-bg-hover-ghost);
  }
  .head {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .title {
    flex: 1;
    min-width: 0;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .latest {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--font-size-sm);
  }
  .latest strong {
    font-weight: 600;
  }
</style>
