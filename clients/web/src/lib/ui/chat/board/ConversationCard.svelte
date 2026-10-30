<script lang="ts">
  import Columns2 from "@lucide/svelte/icons/columns-2";
  import GripVertical from "@lucide/svelte/icons/grip-vertical";
  import Maximize2 from "@lucide/svelte/icons/maximize-2";
  import { DaemonUnavailableError } from "$lib/api/errors";
  import type { ShownMessage } from "$lib/api/types";
  import { cardStatus, lastMessages, type Excerpt } from "$lib/chat/cards";
  import type { ChatSnapshot } from "$lib/chat/controller";
  import { draft } from "$lib/chat/draft.svelte";
  import { fromHistory } from "$lib/chat/transcript";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { markdown } from "$lib/markdown";
  import { describe } from "$lib/notices";
  import Composer from "../Composer.svelte";
  import StatusPill from "./StatusPill.svelte";

  // The messages a card shows, the last ones.
  const EXCERPTS = 4;

  type Props = {
    threadId: string;
    title: string;
    archived: boolean;
    /** When it last changed, as the list of conversations says: what it shows loads again then. */
    updatedAt: string;
    /** This tab's chat on it, which shows it live; null when it isn't open here. */
    live: ChatSnapshot | null;
    /** A reply or a task runs in it, started from anywhere. */
    working: boolean;
    /** The assistant's name, over its messages. */
    name: string;
    /** It's open side by side already. */
    beside: boolean;
    onopen: () => void;
    onbeside: () => void;
    onmaximize: () => void;
    /** Its header is what drags it. */
    ondragstart: (e: DragEvent) => void;
  };
  let { threadId, title, archived, updatedAt, live, working, name, beside, onopen, onbeside, onmaximize, ondragstart }: Props = $props();

  const { client, chats, notices } = useDaemon();
  const box = $derived(draft.of(threadId));
  let card = $state<HTMLElement>();
  let visible = $state(false);
  let history = $state.raw<ShownMessage[]>([]);
  // What the daemon says its run stopped to ask, while it isn't open here.
  let asking = $state(false);
  let error = $state<string | null>(null);
  const isLive = $derived(live !== null);
  const excerpts = $derived(lastMessages(live ? live.transcript.items : fromHistory(history).items, EXCERPTS));
  const status = $derived(cardStatus(live, working, asking));
  const running = $derived(live !== null && (live.busy || live.mirroring));

  // A card loads what it shows once it scrolls into view, so a long list doesn't load every conversation.
  $effect(() => {
    if (!card) return;
    const observer = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting), { rootMargin: "200px" });
    observer.observe(card);
    return () => observer.disconnect();
  });

  // Again when it changes or a run there starts or ends; open here, its chat shows it live instead.
  $effect(() => {
    if (!visible || isLive) return;
    void updatedAt;
    void working;
    let current = true;
    Promise.all([client.conversations.messages(threadId), client.conversations.approvals(threadId)]).then(
      ([messages, waiting]) => {
        if (!current) return;
        history = messages;
        asking = waiting.length > 0;
        error = null;
      },
      (e: unknown) => {
        if (current && !(e instanceof DaemonUnavailableError)) error = describe(e);
      },
    );
    return () => {
      current = false;
    };
  });

  /** Replying opens the conversation in this tab, beside the others, so its reply shows here live. */
  async function reply(text: string, files: File[]): Promise<void> {
    try {
      const chat = await chats.opened(threadId);
      if (!chat) return notices.notify(t("controller.deleted"), "warning");
      const now = chat.getSnapshot();
      if (now.busy || now.mirroring) chat.queue(text, files);
      else await chat.send(text, files);
    } catch (e) {
      notices.report(e);
    }
  }

  function from(excerpt: Excerpt): string {
    if (excerpt.from === "user") return t("board.you");
    if (excerpt.from === "agent") return t("board.task");
    return name;
  }

  // A link in a message opens the link, not the conversation.
  function open(e: MouseEvent): void {
    if (!(e.target instanceof Element && e.target.closest("a"))) onopen();
  }
</script>

<article class="card surface--glass" class:beside bind:this={card} aria-label={title}>
  <!-- Dragging is the mouse's way; the buttons do the same from the keyboard (open side by side). -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <header draggable="true" {ondragstart} title={t("board.move")}>
    <span class="grip" aria-hidden="true"><GripVertical size={14} /></span>
    <button class="title" onclick={onopen} title={t("board.openFull")}>{title}</button>
    <button
      class="btn btn--ghost btn--icon"
      aria-label={t("board.openSide")}
      title={t("board.openSide")}
      aria-pressed={beside}
      onclick={onbeside}><Columns2 size={14} /></button
    >
    <button class="btn btn--ghost btn--icon" aria-label={t("board.maximize")} title={t("board.maximize")} onclick={onmaximize}
      ><Maximize2 size={14} /></button
    >
  </header>
  <div class="state">
    <StatusPill {status} />
    {#if archived}<span class="pill" title={t("conversations.archivedHint")}>{t("conversations.archived")}</span>{/if}
  </div>
  <div
    class="excerpts"
    role="button"
    tabindex="0"
    title={t("board.openFull")}
    onclick={open}
    onkeydown={(e) => e.key === "Enter" && onopen()}
  >
    {#if error}
      <p class="error-text">{error}</p>
    {:else if excerpts.length === 0}
      <p class="text-caption">{t("board.noMessages")}</p>
    {:else}
      {#each excerpts as excerpt (excerpt.id)}
        <div class="excerpt {excerpt.from}">
          <span class="micro-label">{from(excerpt)}</span>
          <div class="text prose">{@html markdown(excerpt.text)}</div>
        </div>
      {/each}
    {/if}
  </div>
  <Composer
    bind:text={box.text}
    bind:files={box.files}
    busy={live?.busy ?? false}
    {running}
    onsend={reply}
    onqueue={reply}
    onstop={() => void chats.find(threadId)?.stop()}
    oncommand={(command) => notices.notify(t("board.commandsInChat", { name: command }), "warning")}
    compact
  />
</article>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    height: 320px;
    padding: 10px 12px 12px;
    min-width: 0;
  }
  .card.beside {
    border-color: color-mix(in srgb, var(--glow) 55%, transparent);
  }
  header {
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    cursor: grab;
    --btn-icon-size: 28px;
  }
  header:active {
    cursor: grabbing;
  }
  header [aria-pressed="true"] {
    color: var(--color-text-primary);
    background: var(--color-bg-hover-ghost);
  }
  .grip {
    display: flex;
    flex: none;
    color: var(--color-text-faint);
  }
  .title {
    flex: 1;
    min-width: 0;
    padding: 0;
    border: 0;
    background: none;
    color: var(--color-text-primary);
    font: inherit;
    font-weight: 600;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }
  .title:hover {
    text-decoration: underline;
  }
  .state {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  /* The newest at the bottom, the older ones fading out at the top. */
  .excerpts {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    gap: 8px;
    overflow: hidden;
    mask-image: linear-gradient(to bottom, transparent, #000 32px);
    cursor: pointer;
    border-radius: var(--radius-sm);
  }
  .excerpts:focus-visible {
    outline: 2px solid color-mix(in srgb, var(--color-text-primary) 40%, transparent);
  }
  .excerpt {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: none;
  }
  .excerpt.user {
    align-items: flex-end;
    text-align: right;
  }
  .text {
    max-height: 4.4em;
    overflow: hidden;
    font-size: var(--font-size-sm);
    line-height: 1.45;
    overflow-wrap: anywhere;
  }
  .user .text {
    padding: 4px 10px;
    border-radius: 12px;
    background: var(--color-bg-hover-ghost);
    max-width: 90%;
  }
  .agent .text {
    border-left: 2px solid var(--color-agent);
    padding-left: 8px;
  }
  .excerpts .text-caption,
  .excerpts .error-text {
    margin: auto;
  }
</style>
