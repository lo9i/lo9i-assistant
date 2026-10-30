<script lang="ts">
  import MessagesSquare from "@lucide/svelte/icons/messages-square";
  import { onMount } from "svelte";
  import type { Conversation } from "$lib/api/types";
  import { beforeOf, movedCard, ordered, restored, toggledMax, unordered, type Layout } from "$lib/chat/cardLayout";
  import { cardStatus } from "$lib/chat/cards";
  import { newestFirst } from "$lib/chat/order";
  import { matching } from "$lib/chat/search";
  import { conversationLayout } from "$lib/conversationLayout.svelte";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { restoresOnEscape } from "$lib/fullScreen";
  import { t } from "$lib/i18n.svelte";
  import { homePins } from "../../homePins.svelte";
  import EmptyState from "../../EmptyState.svelte";
  import SearchField from "../../SearchField.svelte";
  import { openBeside, openConversation } from "../../openConversation";
  import ApprovalModal from "../ApprovalModal.svelte";
  import ConversationCard from "./ConversationCard.svelte";
  import ConversationPane from "./ConversationPane.svelte";

  // The cards view of Chat's list: every conversation as a card with its last messages, status and a small message
  // box, in the order the user dragged them, any one expanded to their whole room. Open beside on a card takes it to the conversation
  // page, next to the conversation shown there (Columns.svelte). The one expanded is a conversation open in this
  // tab (OpenChats), so it's live.
  type Props = { conversations: Conversation[] | undefined; error: string | null };
  let { conversations, error }: Props = $props();

  const CARD_DRAG = "application/x-lo9i-card";

  const { chats, notices } = useDaemon();
  const open = external(chats.subscribe, chats.getSnapshot);
  const runs = resource((c) => c.runs.inProgress(), ["run", "run_finished"]);
  const tasks = resource((c) => c.tasks.running(), ["agent_task_progress", "agent_task_reports", "background_ended"]);
  const name = resource((c) => c.identity.name(), ["settings"]);
  const pins = homePins();

  const layout = $derived(conversationLayout.current);
  const working = $derived(new Set([...(runs.data ?? []), ...(tasks.data ?? [])].map((r) => r.thread_id)));
  const live = $derived(new Map(open.current.chats.map((c) => [c.state.threadId, c.state])));
  const byId = $derived(new Map((conversations ?? []).map((c) => [c.thread_id, c])));
  const order = $derived(
    ordered(
      [...(conversations ?? [])].sort(newestFirst).map((c) => c.thread_id),
      layout.order,
    ),
  );
  let query = $state("");
  const cards = $derived.by(() => {
    const found = new Set(matching(conversations ?? [], query, []).map((c) => c.thread_id));
    return order.filter((id) => found.has(id));
  });
  // The card expanded, in the cards' room.
  const overlay = $derived.by(() => {
    void open.current;
    return layout.maximized === null ? null : chats.find(layout.maximized);
  });
  let dragged: string | null = null;
  let mark = $state<{ id: string; after: boolean } | null>(null);

  function change(next: Layout): void {
    conversationLayout.change(next);
  }

  function titleOf(id: string): string {
    return byId.get(id)?.title || t("nav.newConversation");
  }

  // Full screen is gone once the page is left.
  onMount(() => () => change(restored(conversationLayout.current)));

  async function maximize(id: string): Promise<void> {
    try {
      if (layout.maximized !== id && !(await chats.opened(id))) return notices.notify(t("controller.deleted"), "warning");
      change(toggledMax(conversationLayout.current, id));
    } catch (e) {
      notices.report(e);
    }
  }

  /** /clear in the conversation expanded: a new conversation in its place. */
  async function clearIn(id: string): Promise<void> {
    try {
      const next = (await chats.startNew()).getSnapshot().threadId;
      if (conversationLayout.current.maximized === id) change({ ...conversationLayout.current, maximized: next });
    } catch (e) {
      notices.report(e);
    }
  }

  function keydown(e: KeyboardEvent): void {
    if (conversationLayout.current.maximized !== null && restoresOnEscape(e, document)) change(restored(conversationLayout.current));
  }

  function dragStart(e: DragEvent, id: string): void {
    if (!e.dataTransfer) return;
    dragged = id;
    e.dataTransfer.setData(CARD_DRAG, id);
    e.dataTransfer.effectAllowed = "move";
    const whole = (e.currentTarget as HTMLElement).closest("article");
    if (whole) e.dataTransfer.setDragImage(whole, 16, 16);
  }

  function dragEnd(): void {
    dragged = null;
    mark = null;
  }

  /** Past the middle of the card dragged over: the drop goes after it. */
  function past(e: DragEvent): boolean {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return e.clientX > box.left + box.width / 2;
  }

  function overCard(e: DragEvent, id: string): void {
    if (dragged === null) return;
    e.preventDefault();
    mark = { id, after: past(e) };
  }

  function dropOnCard(e: DragEvent, id: string): void {
    const card = dragged;
    if (card === null) return;
    e.preventDefault();
    change(movedCard(layout, order, card, beforeOf(order, id, past(e))));
    dragEnd();
  }

  function marked(id: string, after: boolean): boolean {
    return mark?.id === id && mark.after === after;
  }
</script>

<svelte:window onkeydown={keydown} ondragend={dragEnd} />

<!-- A card expanded takes the cards' room; they stay as they were, behind it. -->
<section class="cards surface--glass" class:hidden={overlay !== null && layout.maximized !== null}>
  <header class="toolbar">
    <div>
      <h2 class="text-heading">{t("conversations.title")}</h2>
      <p class="text-meta hide-narrow">{t("board.hint")}</p>
    </div>
    <div class="toolbar-actions">
      <SearchField bind:value={query} label={t("conversations.search")} />
      {#if layout.order !== null}
        <button class="btn btn--ghost btn--sm" title={t("board.newestFirstHint")} onclick={() => change(unordered(layout))}
          >{t("board.newestFirst")}</button
        >
      {/if}
    </div>
  </header>
  <div class="scroll">
    {#if error}
      <p class="error-text pad">{error}</p>
    {:else if conversations?.length === 0}
      <EmptyState icon={MessagesSquare} title={t("conversations.noneYet")} text={t("conversations.noneYetHint")} />
    {:else}
      <div class="grid" role="list">
        {#each cards as id (id)}
          {@const conversation = byId.get(id)}
          <div
            class="slot"
            class:drop-before={marked(id, false)}
            class:drop-after={marked(id, true)}
            role="listitem"
            ondragover={(e) => overCard(e, id)}
            ondrop={(e) => dropOnCard(e, id)}
          >
            <ConversationCard
              threadId={id}
              title={titleOf(id)}
              archived={conversation?.archived ?? false}
              updatedAt={conversation?.updated_at ?? ""}
              live={live.get(id) ?? null}
              working={working.has(id)}
              name={name.data || t("chat.theAssistant")}
              pinned={pins.has(id)}
              onpin={() => pins.toggle(id)}
              onopen={() => openConversation(chats, notices, id)}
              onbeside={() => openBeside(chats, notices, conversationLayout, id)}
              onmaximize={() => maximize(id)}
              ondragstart={(e) => dragStart(e, id)}
            />
          </div>
        {/each}
      </div>
    {/if}
  </div>
</section>

{#if overlay && layout.maximized}
  {@const id = layout.maximized}
  <div class="expanded">
    <ConversationPane
      chat={overlay}
      title={titleOf(id)}
      status={cardStatus(live.get(id) ?? null, working.has(id), false)}
      maximized
      findable
      onmaximize={() => maximize(id)}
      onopen={() => openConversation(chats, notices, id)}
      onclear={() => clearIn(id)}
      pinned={pins.has(id)}
      onpin={() => pins.toggle(id)}
    />
  </div>
{/if}

{#if open.current.moving}
  <ApprovalModal approval={open.current.moving} onanswer={(d) => chats.answerMove(d)} />
{/if}

<style>
  .hidden {
    display: none;
  }
  .expanded {
    flex: 1;
    min-width: 0;
    min-height: 0;
  }
  .cards {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 14px 20px;
    min-height: 66px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .pad {
    padding: 24px;
  }
  .scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 14px 16px 16px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }
  .slot {
    position: relative;
    min-width: 0;
  }
  /* Where a dragged card goes: a bar before or after the card under it. */
  .slot.drop-before::before,
  .slot.drop-after::after {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    width: 3px;
    border-radius: 2px;
    background: color-mix(in srgb, var(--glow) 90%, transparent);
    z-index: 1;
  }
  .slot.drop-before::before {
    left: -9px;
  }
  .slot.drop-after::after {
    right: -9px;
  }
</style>
