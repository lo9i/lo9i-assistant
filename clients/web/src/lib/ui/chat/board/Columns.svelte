<script lang="ts">
  import { onMount, untrack } from "svelte";
  import { MediaQuery } from "svelte/reactivity";
  import {
    beforeOf,
    besideOf,
    columnsOf,
    movedPane,
    replacedPane,
    resized,
    restored,
    toggledMax,
    withoutPane,
    type Layout,
  } from "$lib/chat/cardLayout";
  import { cardStatus } from "$lib/chat/cards";
  import { conversationLayout } from "$lib/conversationLayout.svelte";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { NARROW } from "$lib/folderPanel.svelte";
  import { restoresOnEscape } from "$lib/fullScreen";
  import { t } from "$lib/i18n.svelte";
  import { homePins } from "../../homePins.svelte";
  import { CONVERSATION_DRAG } from "../../openConversation";
  import ApprovalModal from "../ApprovalModal.svelte";
  import ChatPanel from "../ChatPanel.svelte";
  import ConversationPane from "./ConversationPane.svelte";

  // The conversation page: the conversation shown, and the ones beside it as columns (conversationLayout), each a
  // conversation open in this tab, live with its own message box: next to each other, or stacked one above the other.
  // Columns are resized by their dividers, reordered by their headers, and any one shows full screen; a conversation
  // dragged from the sidebar opens beside. On a narrow screen one shows at a time, picked from tabs.
  const COLUMN_DRAG = "application/x-lo9i-column";
  // A divider moved from the keyboard, as a share of the width.
  const STEP = 0.02;

  const { chats, hub, notices } = useDaemon();
  const open = external(chats.subscribe, chats.getSnapshot);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const runs = resource((c) => c.runs.inProgress(), ["run", "run_finished"]);
  const tasks = resource((c) => c.tasks.running(), ["agent_task_progress", "agent_task_reports", "background_ended"]);
  const pins = homePins();
  const narrow = new MediaQuery(NARROW);

  const layout = $derived(conversationLayout.current);
  const current = $derived(open.current.chats.find((c) => c.key === open.current.activeKey)?.state.threadId ?? null);
  const working = $derived(new Set([...(runs.data ?? []), ...(tasks.data ?? [])].map((r) => r.thread_id)));
  const live = $derived(new Map(open.current.chats.map((c) => [c.state.threadId, c.state])));
  // The columns whose conversation is open here; the others are being opened again after a reload.
  const columns = $derived.by(() => {
    void open.current;
    if (current === null) return [];
    return columnsOf(layout, current).flatMap((id) => {
      const chat = chats.find(id);
      return chat ? [{ id, chat }] : [];
    });
  });
  // On a narrow screen only the conversation shown, picked from the tabs.
  const shownColumns = $derived(narrow.current ? columns.filter((c) => c.id === current) : columns);
  const stacked = $derived(layout.arrange === "stacked");
  // The column the user was last in; Cmd+F finds there.
  let focused = $state<string | null>(null);
  let dragged: string | null = null;
  let mark = $state<{ id: string | null; after: boolean } | null>(null);
  let row = $state<HTMLElement>();

  function change(next: Layout): void {
    conversationLayout.change(next);
  }

  function titleOf(id: string): string {
    return conversations.data?.find((c) => c.thread_id === id)?.title || t("nav.newConversation");
  }

  // The columns kept from before open again here, and again once the daemon is back if it couldn't be reached; one
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

  // A column whose conversation was open here and closed elsewhere (the sidebar) goes with it.
  const seen = new Set<string>();
  $effect(() => {
    void open.current;
    for (const id of untrack(() => conversationLayout.current.panes)) {
      if (chats.find(id)) seen.add(id);
      else if (seen.delete(id)) change(withoutPane(conversationLayout.current, id));
    }
  });

  /** The column the user is in becomes the conversation shown: the top bar and the sidebar follow it. */
  function show(id: string): void {
    focused = id;
    const key = open.current.chats.find((c) => c.state.threadId === id)?.key;
    if (key !== undefined) chats.activate(key);
  }

  /** `id`, dropped from the sidebar, opens beside the conversation shown, before `before` (at the end for null). */
  async function addBeside(id: string, before: string | null): Promise<void> {
    if (current === null) return;
    const anchor = current;
    try {
      if (!(await chats.opened(id))) return notices.notify(t("controller.deleted"), "warning");
      const added = besideOf(conversationLayout.current, anchor, id);
      change(before === null ? added : movedPane(added, id, before));
    } catch (e) {
      notices.report(e);
    }
  }

  /** Closing a column; the conversation stays open, in the sidebar. The shown one gives way to the one beside it. */
  function close(id: string): void {
    const next = withoutPane(layout, id);
    change(next);
    if (id === current && next.panes[0]) show(next.panes[0]);
  }

  /** /clear in a column: a new conversation in its place. */
  async function clearIn(id: string): Promise<void> {
    try {
      const next = (await chats.startNew()).getSnapshot().threadId;
      change(replacedPane(conversationLayout.current, id, next));
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
    e.dataTransfer.setData(COLUMN_DRAG, id);
    e.dataTransfer.effectAllowed = "move";
    const whole = (e.currentTarget as HTMLElement).closest("section");
    if (whole) e.dataTransfer.setDragImage(whole, 16, 16);
  }

  function dragEnd(): void {
    dragged = null;
    mark = null;
  }

  /** A column being moved, or a conversation from the sidebar. */
  function droppable(e: DragEvent): boolean {
    return dragged !== null || Array.from(e.dataTransfer?.types ?? []).includes(CONVERSATION_DRAG);
  }

  /** Past the middle of what's dragged over (its lower half, stacked): the drop goes after it. */
  function past(e: DragEvent): boolean {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return stacked ? e.clientY > box.top + box.height / 2 : e.clientX > box.left + box.width / 2;
  }

  /** Over a column, or the page at the end (`id` null). */
  function over(e: DragEvent, id: string | null): void {
    if (!droppable(e)) return;
    e.preventDefault();
    e.stopPropagation();
    mark = { id, after: id === null || past(e) };
  }

  function drop(e: DragEvent, id: string | null): void {
    if (!droppable(e)) return;
    e.preventDefault();
    e.stopPropagation();
    const moving = dragged;
    const before = id === null || columns.length < 2 ? null : beforeOf(layout.panes, id, past(e));
    const conversation = e.dataTransfer?.getData(CONVERSATION_DRAG) ?? "";
    dragEnd();
    if (moving !== null) change(movedPane(layout, moving, before));
    else if (conversation) void addBeside(conversation, before);
  }

  function marked(id: string | null, after: boolean): boolean {
    return mark?.id === id && mark.after === after;
  }

  /** Dragging a divider: across, side by side; up and down, stacked. */
  function startResize(e: PointerEvent, index: number): void {
    const divider = e.currentTarget as HTMLElement;
    const length = (stacked ? row?.clientHeight : row?.clientWidth) ?? 0;
    if (length === 0) return;
    divider.setPointerCapture(e.pointerId);
    const along = (p: PointerEvent) => (stacked ? p.clientY : p.clientX);
    const start = along(e);
    const widths = layout.widths;
    const move = (m: PointerEvent) =>
      change({ ...conversationLayout.current, widths: resized(widths, index, (along(m) - start) / length) });
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
    const steps: Record<string, number> = stacked ? { ArrowUp: -STEP, ArrowDown: STEP } : { ArrowLeft: -STEP, ArrowRight: STEP };
    if (!(e.key in steps)) return;
    e.preventDefault();
    change({ ...layout, widths: resized(layout.widths, index, steps[e.key]) });
  }
</script>

<svelte:window onkeydown={keydown} ondragend={dragEnd} />

<div class="columns-page" class:narrow={narrow.current}>
  {#if narrow.current && columns.length > 1}
    <div class="tabs" role="tablist" aria-label={t("board.sideBySide")}>
      {#each columns as c (c.id)}
        <button role="tab" class="btn btn--sm" class:on={c.id === current} aria-selected={c.id === current} onclick={() => show(c.id)}
          >{titleOf(c.id)}</button
        >
      {/each}
    </div>
  {/if}

  <div
    class="row"
    class:stacked
    class:drop-end={marked(null, true)}
    bind:this={row}
    role="group"
    aria-label={t("board.sideBySide")}
    ondragover={(e) => over(e, null)}
    ondragleave={(e) => !e.currentTarget.contains(e.relatedTarget as Node | null) && (mark = null)}
    ondrop={(e) => drop(e, null)}
  >
    {#if columns.length < 2}
      <!-- One conversation: as it always showed, without a column's header. -->
      <div class="single"><ChatPanel /></div>
    {:else}
      {#each shownColumns as c, i (c.id)}
        {#if i > 0}
          <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
          <div
            class="divider"
            role="separator"
            aria-orientation={stacked ? "horizontal" : "vertical"}
            aria-label={t("board.resize")}
            aria-valuenow={Math.round((layout.widths[i - 1] ?? 0) * 100)}
            tabindex="0"
            title={t("board.resize")}
            onpointerdown={(e) => startResize(e, i - 1)}
            onkeydown={(e) => resizeKey(e, i - 1)}
          ></div>
        {/if}
        <div
          class="slot"
          class:shown={c.id === current}
          class:drop-before={marked(c.id, false)}
          class:drop-after={marked(c.id, true)}
          style:flex="{narrow.current ? 1 : (layout.widths[layout.panes.indexOf(c.id)] ?? 1)} 1 0"
          role="presentation"
          onfocusin={() => show(c.id)}
          ondragover={(e) => over(e, c.id)}
          ondrop={(e) => drop(e, c.id)}
        >
          <ConversationPane
            chat={c.chat}
            title={titleOf(c.id)}
            status={cardStatus(live.get(c.id) ?? null, working.has(c.id), false)}
            maximized={layout.maximized === c.id}
            findable={layout.maximized === null ? (focused ?? current) === c.id : layout.maximized === c.id}
            onmaximize={() => change(toggledMax(layout, c.id))}
            onclear={() => clearIn(c.id)}
            pinned={pins.has(c.id)}
            onpin={() => pins.toggle(c.id)}
            onclose={() => close(c.id)}
            ondragstart={narrow.current ? undefined : (e) => dragStart(e, c.id)}
          />
        </div>
      {/each}
    {/if}
  </div>
</div>

{#if columns.length > 1 && open.current.moving}
  <ApprovalModal approval={open.current.moving} onanswer={(d) => chats.answerMove(d)} />
{/if}

<style>
  .columns-page {
    display: flex;
    flex-direction: column;
    gap: 8px;
    height: 100%;
    min-height: 0;
  }
  .tabs {
    flex: none;
    display: flex;
    gap: 4px;
    overflow-x: auto;
  }
  .tabs .btn {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--color-text-muted);
  }
  .tabs .btn.on {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  .row {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
  }
  .single {
    flex: 1;
    min-width: 0;
    min-height: 0;
  }
  .slot {
    position: relative;
    min-width: 0;
    min-height: 0;
  }
  /* The conversation shown, which the top bar names. */
  .slot.shown :global(.pane > header h2) {
    color: var(--color-text-primary);
  }
  .slot:not(.shown) :global(.pane > header h2) {
    color: var(--color-text-muted);
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
  /* Stacked, one above the other: the dividers run across and are dragged up and down. */
  .row.stacked {
    flex-direction: column;
  }
  .stacked > .divider {
    width: auto;
    height: 12px;
    cursor: row-resize;
  }
  .stacked > .divider::after {
    top: 5px;
    bottom: auto;
    left: 30%;
    right: 30%;
    width: auto;
    height: 2px;
  }
  /* Where a drop goes: a bar before or after a column, or at the page's right end. */
  .slot.drop-before::before,
  .slot.drop-after::after,
  .row.drop-end::after {
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
  .slot.drop-after::after {
    right: -7px;
  }
  .row.drop-end::after {
    right: 0;
  }
  .stacked > .slot.drop-before::before,
  .stacked > .slot.drop-after::after,
  .row.stacked.drop-end::after {
    left: 0;
    right: 0;
    width: auto;
    height: 3px;
  }
  .stacked > .slot.drop-before::before {
    top: -7px;
    bottom: auto;
  }
  .stacked > .slot.drop-after::after {
    top: auto;
    bottom: -7px;
  }
  .row.stacked.drop-end::after {
    top: auto;
    bottom: 0;
  }
</style>
