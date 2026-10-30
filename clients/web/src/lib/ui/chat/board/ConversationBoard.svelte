<script lang="ts">
  import LayoutGrid from "@lucide/svelte/icons/layout-grid";
  import MessagesSquare from "@lucide/svelte/icons/messages-square";
  import PanelRightClose from "@lucide/svelte/icons/panel-right-close";
  import PanelRightOpen from "@lucide/svelte/icons/panel-right-open";
  import { onMount, untrack } from "svelte";
  import { MediaQuery } from "svelte/reactivity";
  import type { Conversation } from "$lib/api/types";
  import {
    beforeOf,
    MAX_PANES,
    movedCard,
    movedPane,
    ordered,
    replacedPane,
    resized,
    restored,
    toggledMax,
    unordered,
    withoutPane,
    withPane,
    type Layout,
  } from "$lib/chat/cardLayout";
  import { cardStatus } from "$lib/chat/cards";
  import { newestFirst } from "$lib/chat/order";
  import { matching } from "$lib/chat/search";
  import { conversationLayout } from "$lib/conversationLayout.svelte";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { NARROW } from "$lib/folderPanel.svelte";
  import { t } from "$lib/i18n.svelte";
  import EmptyState from "../../EmptyState.svelte";
  import SearchField from "../../SearchField.svelte";
  import { openConversation } from "../../openConversation";
  import ApprovalModal from "../ApprovalModal.svelte";
  import ConversationCard from "./ConversationCard.svelte";
  import ConversationPane from "./ConversationPane.svelte";

  // The cards view of Chat's page: every conversation as a card, some of them side by side as panes, any one full
  // screen. Panes and the one full screen are conversations open in this tab (OpenChats), so they're live and each
  // has its own composer; the layout is kept per browser (conversationLayout).
  type Props = { conversations: Conversation[] | undefined; error: string | null };
  let { conversations, error }: Props = $props();

  // What a drag carries, for browsers that need data set to drag at all; the page knows what it drags meanwhile.
  const MIME = { card: "application/x-lo9i-card", pane: "application/x-lo9i-pane" };
  // A divider moved from the keyboard, as a share of the width.
  const STEP = 0.02;

  const { chats, hub, notices } = useDaemon();
  const open = external(chats.subscribe, chats.getSnapshot);
  const runs = resource((c) => c.runs.inProgress(), ["run", "run_finished"]);
  const tasks = resource((c) => c.tasks.running(), ["agent_task_progress", "agent_task_reports", "background_ended"]);
  const name = resource((c) => c.identity.name(), ["settings"]);
  const narrow = new MediaQuery(NARROW);

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
  // The panes whose conversation is open here; the others are being opened again after a reload.
  const panes = $derived.by(() => {
    void open.current;
    return layout.panes.flatMap((id) => {
      const chat = chats.find(id);
      return chat ? [{ id, chat }] : [];
    });
  });
  // On a narrow screen one conversation at a time: the cards (null), or one of the panes.
  let narrowShown = $state<string | null>(null);
  const shownPanes = $derived(narrow.current ? panes.filter((p) => p.id === narrowShown) : panes);
  const cardsShown = $derived(narrow.current ? shownPanes.length === 0 : panes.length === 0 || layout.cardsBeside);
  // A card full screen shows over the page: it isn't a pane shown.
  const overlay = $derived.by(() => {
    void open.current;
    const id = layout.maximized;
    return id !== null && !shownPanes.some((p) => p.id === id) ? chats.find(id) : null;
  });
  // The pane the user was last in; Cmd+F finds there.
  let focused = $state<string | null>(null);
  let dragged: { kind: keyof typeof MIME; id: string } | null = null;
  let mark = $state<{ area: "cards" | "panes"; id: string | null; after: boolean } | null>(null);
  let panesEl = $state<HTMLElement>();

  function change(next: Layout): void {
    conversationLayout.change(next);
  }

  function titleOf(id: string): string {
    return byId.get(id)?.title || t("nav.newConversation");
  }

  function statusOf(id: string) {
    return cardStatus(live.get(id) ?? null, working.has(id), false);
  }

  // The panes kept from before open again here, and again once the daemon is back if it couldn't be reached; one
  // that's gone (deleted, the inbox) closes. Full screen is gone once the page is left.
  onMount(() => {
    void restore();
    return () => change(restored(conversationLayout.current));
  });
  $effect(() => hub.onReconnect(() => void restore()));

  async function restore(): Promise<void> {
    for (const id of untrack(() => conversationLayout.current.panes)) {
      try {
        if (!(await chats.opened(id))) change(withoutPane(conversationLayout.current, id));
      } catch (e) {
        notices.report(e);
      }
    }
  }

  // A pane whose conversation was open here and closed elsewhere (the sidebar) goes with it.
  const seen = new Set<string>();
  $effect(() => {
    void open.current;
    for (const id of untrack(() => conversationLayout.current.panes)) {
      if (chats.find(id)) seen.add(id);
      else if (seen.delete(id)) change(withoutPane(conversationLayout.current, id));
    }
  });

  async function addPane(id: string, before: string | null = null): Promise<void> {
    try {
      if (!(await chats.opened(id))) return notices.notify(t("controller.deleted"), "warning");
      change(withPane(conversationLayout.current, id, before));
      narrowShown = id;
    } catch (e) {
      notices.report(e);
    }
  }

  function toggleBeside(id: string): void {
    if (layout.panes.includes(id)) change(withoutPane(layout, id));
    else void addPane(id);
  }

  async function maximize(id: string): Promise<void> {
    try {
      if (layout.maximized !== id && !(await chats.opened(id))) return notices.notify(t("controller.deleted"), "warning");
      change(toggledMax(conversationLayout.current, id));
    } catch (e) {
      notices.report(e);
    }
  }

  /** /clear in a pane, or in the conversation full screen: a new conversation in its place. */
  async function clearIn(id: string): Promise<void> {
    try {
      const next = (await chats.startNew()).getSnapshot().threadId;
      const now = conversationLayout.current;
      change(now.panes.includes(id) ? replacedPane(now, id, next) : { ...now, maximized: now.maximized === id ? next : now.maximized });
      if (narrowShown === id) narrowShown = next;
    } catch (e) {
      notices.report(e);
    }
  }

  function keydown(e: KeyboardEvent): void {
    if (e.key !== "Escape" || e.defaultPrevented || conversationLayout.current.maximized === null) return;
    // A dialog's Esc closes the dialog.
    if (document.querySelector('[role="dialog"]')) return;
    change(restored(conversationLayout.current));
  }

  function dragStart(e: DragEvent, kind: keyof typeof MIME, id: string): void {
    if (!e.dataTransfer) return;
    dragged = { kind, id };
    e.dataTransfer.setData(MIME[kind], id);
    e.dataTransfer.effectAllowed = "move";
    const whole = (e.currentTarget as HTMLElement).closest("article, section");
    if (whole) e.dataTransfer.setDragImage(whole, 16, 16);
  }

  function dragEnd(): void {
    dragged = null;
    mark = null;
  }

  /** Past the middle of what's dragged over: the drop goes after it. */
  function past(e: DragEvent): boolean {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return e.clientX > box.left + box.width / 2;
  }

  function overCard(e: DragEvent, id: string): void {
    if (dragged?.kind !== "card") return;
    e.preventDefault();
    mark = { area: "cards", id, after: past(e) };
  }

  function dropOnCard(e: DragEvent, id: string): void {
    const card = dragged;
    if (card?.kind !== "card") return;
    e.preventDefault();
    change(movedCard(layout, order, card.id, beforeOf(order, id, past(e))));
    dragEnd();
  }

  /** Over a pane, or the side-by-side area at the end (`id` null): a card opens there, a pane moves there. */
  function overPanes(e: DragEvent, id: string | null): void {
    if (!dragged) return;
    e.preventDefault();
    e.stopPropagation();
    mark = { area: "panes", id, after: id === null || past(e) };
  }

  function dropOnPanes(e: DragEvent, id: string | null): void {
    const what = dragged;
    if (!what) return;
    e.preventDefault();
    e.stopPropagation();
    const before = id === null ? null : beforeOf(layout.panes, id, past(e));
    dragEnd();
    if (what.kind === "pane") change(movedPane(layout, what.id, before));
    else void addPane(what.id, before);
  }

  function marked(area: "cards" | "panes", id: string | null, after: boolean): boolean {
    return mark?.area === area && mark.id === id && mark.after === after;
  }

  function startResize(e: PointerEvent, index: number): void {
    const divider = e.currentTarget as HTMLElement;
    const width = panesEl?.clientWidth ?? 0;
    if (width === 0) return;
    divider.setPointerCapture(e.pointerId);
    const start = e.clientX;
    const widths = layout.widths;
    const move = (m: PointerEvent) =>
      change({ ...conversationLayout.current, widths: resized(widths, index, (m.clientX - start) / width) });
    const end = () => {
      divider.removeEventListener("pointermove", move);
      divider.removeEventListener("pointerup", end);
      divider.removeEventListener("pointercancel", end);
    };
    divider.addEventListener("pointermove", move);
    divider.addEventListener("pointerup", end);
    divider.addEventListener("pointercancel", end);
  }

  function resizeKey(e: KeyboardEvent, index: number): void {
    const steps: Record<string, number> = { ArrowLeft: -STEP, ArrowRight: STEP };
    if (!(e.key in steps)) return;
    e.preventDefault();
    change({ ...layout, widths: resized(layout.widths, index, steps[e.key]) });
  }
</script>

<svelte:window onkeydown={keydown} ondragend={dragEnd} />

<div class="board" class:narrow={narrow.current}>
  {#if narrow.current && panes.length}
    <div class="strip" role="tablist" aria-label={t("board.sideBySide")}>
      <button
        role="tab"
        class="btn btn--sm"
        class:on={shownPanes.length === 0}
        aria-selected={shownPanes.length === 0}
        onclick={() => (narrowShown = null)}><LayoutGrid size={14} />{t("board.cards")}</button
      >
      {#each panes as p (p.id)}
        <button
          role="tab"
          class="btn btn--sm"
          class:on={narrowShown === p.id}
          aria-selected={narrowShown === p.id}
          onclick={() => (narrowShown = p.id)}>{titleOf(p.id)}</button
        >
      {/each}
    </div>
  {/if}

  {#if shownPanes.length}
    <div
      class="panes"
      class:drop-end={marked("panes", null, true)}
      bind:this={panesEl}
      role="group"
      aria-label={t("board.sideBySide")}
      ondragover={(e) => overPanes(e, null)}
      ondrop={(e) => dropOnPanes(e, null)}
    >
      {#each shownPanes as p, i (p.id)}
        {#if i > 0}
          <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
          <div
            class="divider"
            role="separator"
            aria-orientation="vertical"
            aria-label={t("board.resize")}
            aria-valuenow={Math.round(layout.widths[i - 1] * 100)}
            tabindex="0"
            title={t("board.resize")}
            onpointerdown={(e) => startResize(e, i - 1)}
            onkeydown={(e) => resizeKey(e, i - 1)}
          ></div>
        {/if}
        <div
          class="slot"
          class:drop-before={marked("panes", p.id, false)}
          class:drop-after={marked("panes", p.id, true)}
          style:flex="{narrow.current ? 1 : (layout.widths[layout.panes.indexOf(p.id)] ?? 1)} 1 0"
          role="presentation"
          onfocusin={() => (focused = p.id)}
          ondragover={(e) => overPanes(e, p.id)}
          ondrop={(e) => dropOnPanes(e, p.id)}
        >
          <ConversationPane
            chat={p.chat}
            title={titleOf(p.id)}
            status={statusOf(p.id)}
            maximized={layout.maximized === p.id}
            findable={layout.maximized === null ? (focused ?? shownPanes[0].id) === p.id : layout.maximized === p.id}
            onmaximize={() => maximize(p.id)}
            onopen={() => openConversation(chats, notices, p.id)}
            onclear={() => clearIn(p.id)}
            onclose={() => change(withoutPane(layout, p.id))}
            ondragstart={narrow.current ? undefined : (e) => dragStart(e, "pane", p.id)}
          />
        </div>
      {/each}
    </div>
  {/if}

  {#if cardsShown}
    <section class="cards surface--glass" class:rail={!narrow.current && shownPanes.length > 0}>
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
          {#if !narrow.current && panes.length}
            <button
              class="btn btn--ghost btn--icon btn--sm"
              aria-label={t("board.hideCards")}
              title={t("board.hideCards")}
              onclick={() => change({ ...layout, cardsBeside: false })}><PanelRightClose size={16} /></button
            >
          {/if}
        </div>
      </header>
      {#if !narrow.current && panes.length === 0}
        <div
          class="dropzone"
          class:over={marked("panes", null, true)}
          role="group"
          aria-label={t("board.sideBySide")}
          ondragover={(e) => overPanes(e, null)}
          ondrop={(e) => dropOnPanes(e, null)}
        >
          {t("board.dropHere", { count: MAX_PANES })}
        </div>
      {/if}
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
                class:drop-before={marked("cards", id, false)}
                class:drop-after={marked("cards", id, true)}
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
                  beside={layout.panes.includes(id)}
                  onopen={() => openConversation(chats, notices, id)}
                  onbeside={() => toggleBeside(id)}
                  onmaximize={() => maximize(id)}
                  ondragstart={(e) => dragStart(e, "card", id)}
                />
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </section>
  {:else if !narrow.current}
    <button
      class="btn btn--ghost btn--icon btn--sm show-cards"
      aria-label={t("board.showCards")}
      title={t("board.showCards")}
      onclick={() => change({ ...layout, cardsBeside: true })}><PanelRightOpen size={16} /></button
    >
  {/if}
</div>

{#if overlay && layout.maximized}
  {@const id = layout.maximized}
  <ConversationPane
    chat={overlay}
    title={titleOf(id)}
    status={statusOf(id)}
    maximized
    findable
    onmaximize={() => maximize(id)}
    onopen={() => openConversation(chats, notices, id)}
    onclear={() => clearIn(id)}
  />
{/if}

{#if open.current.moving}
  <ApprovalModal approval={open.current.moving} onanswer={(d) => chats.answerMove(d)} />
{/if}

<style>
  .board {
    flex: 1;
    min-height: 0;
    display: flex;
    gap: 12px;
  }
  .board.narrow {
    flex-direction: column;
    gap: 8px;
  }
  .strip {
    flex: none;
    display: flex;
    gap: 4px;
    overflow-x: auto;
  }
  .strip .btn {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--color-text-muted);
  }
  .strip .btn.on {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  .panes {
    position: relative;
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
  }
  .panes > .slot {
    position: relative;
    min-width: 0;
    min-height: 0;
  }
  .divider {
    flex: none;
    width: 12px;
    cursor: col-resize;
    touch-action: none;
    position: relative;
  }
  .divider::after {
    content: "";
    position: absolute;
    top: 30%;
    bottom: 30%;
    left: 5px;
    width: 2px;
    border-radius: 1px;
    background: var(--color-border);
    transition: background 0.12s ease;
  }
  .divider:hover::after,
  .divider:focus-visible::after {
    background: color-mix(in srgb, var(--glow) 80%, transparent);
  }
  .divider:focus-visible {
    outline: none;
  }
  /* Where a drop goes: a bar before or after a pane or a card, or at the end of the panes. */
  .slot.drop-before::before,
  .slot.drop-after::after,
  .panes.drop-end::after {
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
    left: -7px;
  }
  .slot.drop-after::after,
  .panes.drop-end::after {
    right: -7px;
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
  .pad {
    padding: 24px;
  }
  .cards.rail {
    flex: 0 0 340px;
  }
  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .rail .toolbar {
    flex-wrap: wrap;
  }
  .rail .text-meta {
    display: none;
  }
  .dropzone {
    margin: 12px 16px 4px;
    padding: 14px;
    border: 1.5px dashed var(--color-border);
    border-radius: var(--radius-md);
    color: var(--color-text-faint);
    font-size: var(--font-size-sm);
    text-align: center;
    transition:
      border-color 0.12s ease,
      background 0.12s ease;
  }
  .dropzone.over {
    border-color: color-mix(in srgb, var(--glow) 80%, transparent);
    background: color-mix(in srgb, var(--glow) 10%, transparent);
    color: var(--color-text-primary);
  }
  .scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 4px 16px 16px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }
  .grid > .slot {
    position: relative;
    min-width: 0;
  }
  .show-cards {
    align-self: flex-start;
    flex: none;
  }
</style>
