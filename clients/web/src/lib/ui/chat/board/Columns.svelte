<script lang="ts">
  import { onMount, untrack } from "svelte";
  import { MediaQuery } from "svelte/reactivity";
  import {
    atEnd,
    besideOf,
    docked,
    edgeOf,
    groupsOf,
    replacedPane,
    resizedGroups,
    resizedWithin,
    restored,
    toggledMax,
    together,
    withoutPane,
    type Edge,
    type Layout,
  } from "$lib/chat/cardLayout";
  import { cardStatus } from "$lib/chat/cards";
  import type { ChatController } from "$lib/chat/controller";
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

  // The conversation page: the conversation shown, and the ones together with it (conversationLayout), each a
  // conversation open in this tab, live with its own message box. They sit in groups: columns side by side, each
  // holding one or more stacked, or rows stacked, each holding one or more side by side; so the page can be split in
  // half with two stacked in one half. Dividers resize them both ways, and any one shows full screen. A conversation
  // dragged by its header, or from the sidebar, dropped on one takes the half of it it's dropped on (docked). On a
  // narrow screen one shows at a time, picked from tabs.
  const COLUMN_DRAG = "application/x-lo9i-column";
  /** What dragging a divider by `delta` (a share of the room) does to `base`, the layout it's measured from. */
  type Resizing = (base: Layout, delta: number) => Layout;
  // A divider moved from the keyboard, as a share of the room.
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
  // The groups shown, each with its conversations open here and their shares; the others are being opened again
  // after a reload.
  const groups = $derived.by(() => {
    void open.current;
    if (current === null) return [];
    return groupsOf(layout, current)
      .map((g, index) => ({
        index,
        share: layout.shares[index] ?? 1,
        items: g.ids.flatMap((id, i) => {
          const chat = chats.find(id);
          return chat ? [{ id, chat, share: g.shares[i] ?? 1 }] : [];
        }),
      }))
      .filter((g) => g.items.length > 0);
  });
  const items = $derived(groups.flatMap((g) => g.items));
  const stacked = $derived(layout.arrange === "stacked");
  // The one expanded to the whole room, the others hidden (kept as they are, so they come back where they were).
  const expanded = $derived(items.some((item) => item.id === layout.maximized) ? layout.maximized : null);
  // The one the user was last in; Cmd+F finds there.
  let focused = $state<string | null>(null);
  let dragged: string | null = null;
  // Where a drop would go: an edge of the conversation dragged over, or the page's end (`id` null).
  let mark = $state<{ id: string | null; edge: Edge } | null>(null);

  function change(next: Layout): void {
    conversationLayout.change(next);
  }

  function titleOf(id: string): string {
    return conversations.data?.find((c) => c.thread_id === id)?.title || t("nav.newConversation");
  }

  // The conversations kept from before open again here, and again once the daemon is back if it couldn't be reached;
  // one that's gone (deleted, the inbox) closes. Full screen is gone once the page is left.
  onMount(() => {
    void restore();
    return () => change(restored(conversationLayout.current));
  });
  $effect(() => hub.onReconnect(() => void restore()));

  async function restore(): Promise<void> {
    for (const id of untrack(() => together(conversationLayout.current))) {
      try {
        if (!(await chats.opened(id))) change(withoutPane(conversationLayout.current, id));
      } catch (e) {
        notices.report(e);
      }
    }
  }

  // One that was open here and closed elsewhere (the sidebar) goes with it.
  const seen = new Set<string>();
  $effect(() => {
    void open.current;
    for (const id of untrack(() => together(conversationLayout.current))) {
      if (chats.find(id)) seen.add(id);
      else if (seen.delete(id)) change(withoutPane(conversationLayout.current, id));
    }
  });

  /** The one the user is in becomes the conversation shown: the sidebar follows it. */
  function show(id: string): void {
    focused = id;
    const key = open.current.chats.find((c) => c.state.threadId === id)?.key;
    if (key !== undefined) chats.activate(key);
  }

  /** `id`, dropped from the sidebar at the page's end, opens beside the conversation shown. */
  async function addBeside(id: string): Promise<void> {
    if (current === null) return;
    const anchor = current;
    try {
      if (!(await chats.opened(id))) return notices.notify(t("controller.deleted"), "warning");
      change(besideOf(conversationLayout.current, anchor, id));
    } catch (e) {
      notices.report(e);
    }
  }

  /** `id`, dropped from the sidebar at `edge` of the conversation `target`, opens there. */
  async function addAt(target: string, id: string, edge: Edge): Promise<void> {
    try {
      if (!(await chats.opened(id))) return notices.notify(t("controller.deleted"), "warning");
      change(docked(conversationLayout.current, target, id, edge));
    } catch (e) {
      notices.report(e);
    }
  }

  /** Closing one; the conversation stays open, in the sidebar. The shown one gives way to another still here. */
  function close(id: string): void {
    const next = withoutPane(layout, id);
    change(next);
    const other = together(next)[0];
    if (id === current && other) show(other);
  }

  /** /clear in one: a new conversation in its place. */
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

  /** One shown being moved, or a conversation from the sidebar. */
  function droppable(e: DragEvent): boolean {
    return dragged !== null || Array.from(e.dataTransfer?.types ?? []).includes(CONVERSATION_DRAG);
  }

  /** The edge of what's dragged over that the pointer is nearest. */
  function edge(e: DragEvent): Edge {
    return edgeOf((e.currentTarget as HTMLElement).getBoundingClientRect(), e.clientX, e.clientY);
  }

  /** Over a conversation (`id`), or the page around them (`id` null, the end). One isn't dropped on itself. */
  function over(e: DragEvent, id: string | null): void {
    if (!droppable(e)) return;
    e.stopPropagation();
    if (id !== null && id === dragged) return void (mark = null);
    e.preventDefault();
    mark = { id, edge: id === null ? (stacked ? "bottom" : "right") : edge(e) };
  }

  function drop(e: DragEvent, id: string | null): void {
    if (!droppable(e)) return;
    e.stopPropagation();
    if (id !== null && id === dragged) return dragEnd();
    e.preventDefault();
    const moving = dragged;
    const conversation = e.dataTransfer?.getData(CONVERSATION_DRAG) ?? "";
    const at = id === null ? null : edge(e);
    dragEnd();
    if (id !== null && at !== null) {
      if (moving !== null) change(docked(layout, id, moving, at));
      else if (conversation) void addAt(id, conversation, at);
    } else if (moving !== null) change(atEnd(layout, moving));
    else if (conversation) void addBeside(conversation);
  }

  function dropAt(id: string): Edge | null {
    return mark?.id === id ? mark.edge : null;
  }

  /** Dragging a divider `across` (left and right) or not (up and down), in the room it divides; `resizing` says what
   * changes. */
  function startResize(e: PointerEvent, across: boolean, resizing: Resizing): void {
    const divider = e.currentTarget as HTMLElement;
    const room = divider.parentElement;
    const length = (across ? room?.clientWidth : room?.clientHeight) ?? 0;
    if (length === 0) return;
    divider.setPointerCapture(e.pointerId);
    const along = (p: PointerEvent) => (across ? p.clientX : p.clientY);
    const start = along(e);
    // Each move measures from where the drag started, on the layout as it was then: applied to the layout already
    // moved, the distance would add up and send the divider to the end.
    const before = conversationLayout.current;
    const move = (m: PointerEvent) => change(resizing(before, (along(m) - start) / length));
    const end = () => {
      divider.removeEventListener("pointermove", move);
      divider.removeEventListener("pointerup", end);
      divider.removeEventListener("pointercancel", end);
    };
    divider.addEventListener("pointermove", move);
    divider.addEventListener("pointerup", end);
    divider.addEventListener("pointercancel", end);
  }

  function resizeKey(e: KeyboardEvent, across: boolean, resizing: Resizing): void {
    const steps: Record<string, number> = across ? { ArrowLeft: -STEP, ArrowRight: STEP } : { ArrowUp: -STEP, ArrowDown: STEP };
    if (!(e.key in steps)) return;
    e.preventDefault();
    change(resizing(conversationLayout.current, steps[e.key]));
  }
</script>

<svelte:window onkeydown={keydown} ondragend={dragEnd} />

{#snippet divider(across: boolean, share: number, resizing: Resizing)}
  <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
  <div
    class="divider"
    class:across
    role="separator"
    aria-orientation={across ? "vertical" : "horizontal"}
    aria-label={t("board.resize")}
    aria-valuenow={Math.round(share * 100)}
    tabindex="0"
    title={t("board.resize")}
    onpointerdown={(e) => startResize(e, across, resizing)}
    onkeydown={(e) => resizeKey(e, across, resizing)}
  ></div>
{/snippet}

{#snippet pane(id: string, chat: ChatController, share: number)}
  <div
    class="slot"
    class:shown={id === current}
    class:hidden={expanded !== null && id !== expanded}
    data-drop={dropAt(id)}
    style:flex="{id === expanded ? 1 : share} 1 0"
    role="presentation"
    onfocusin={() => show(id)}
    ondragover={(e) => over(e, id)}
    ondrop={(e) => drop(e, id)}
  >
    <ConversationPane
      {chat}
      title={titleOf(id)}
      status={cardStatus(live.get(id) ?? null, working.has(id), false)}
      maximized={layout.maximized === id}
      findable={layout.maximized === null ? (focused ?? current) === id : layout.maximized === id}
      onmaximize={() => change(toggledMax(layout, id))}
      onclear={() => clearIn(id)}
      pinned={pins.has(id)}
      onpin={() => pins.toggle(id)}
      onclose={() => close(id)}
      ondragstart={narrow.current ? undefined : (e) => dragStart(e, id)}
    />
  </div>
{/snippet}

<div class="columns-page">
  {#if narrow.current && items.length > 1}
    <div class="tabs" role="tablist" aria-label={t("board.sideBySide")}>
      {#each items as item (item.id)}
        <button
          role="tab"
          class="btn btn--sm"
          class:on={item.id === current}
          aria-selected={item.id === current}
          onclick={() => show(item.id)}>{titleOf(item.id)}</button
        >
      {/each}
    </div>
  {/if}

  <div
    class="row"
    class:stacked
    class:drop-end={mark?.id === null}
    role="group"
    aria-label={t("board.sideBySide")}
    ondragover={(e) => over(e, null)}
    ondragleave={(e) => !e.currentTarget.contains(e.relatedTarget as Node | null) && (mark = null)}
    ondrop={(e) => drop(e, null)}
  >
    {#if items.length < 2}
      <!-- One conversation: as it always showed, without a header of its own. -->
      <div
        class="single"
        data-drop={current ? dropAt(current) : null}
        role="presentation"
        ondragover={(e) => over(e, current)}
        ondrop={(e) => drop(e, current)}
      >
        <ChatPanel />
      </div>
    {:else if narrow.current}
      {#each items.filter((item) => item.id === current) as item (item.id)}
        {@render pane(item.id, item.chat, 1)}
      {/each}
    {:else}
      {#each groups as group, g (group.index)}
        {#if g > 0 && expanded === null}
          {@render divider(!stacked, group.share, (base, delta) => resizedGroups(base, group.index - 1, delta))}
        {/if}
        <div
          class="group"
          class:hidden={expanded !== null && !group.items.some((item) => item.id === expanded)}
          style:flex="{group.items.some((item) => item.id === expanded) ? 1 : group.share} 1 0"
        >
          {#each group.items as item, i (item.id)}
            {#if i > 0 && expanded === null}
              {@render divider(stacked, item.share, (base, delta) => resizedWithin(base, group.index, i - 1, delta))}
            {/if}
            {@render pane(item.id, item.chat, item.share)}
          {/each}
        </div>
      {/each}
    {/if}
  </div>
</div>

{#if items.length > 1 && open.current.moving}
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
  /* Groups side by side, each stacking its conversations; stacked, each row has them side by side. */
  .row {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
  }
  .row.stacked {
    flex-direction: column;
  }
  .group {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .stacked > .group {
    flex-direction: row;
  }
  .single {
    position: relative;
    flex: 1;
    min-width: 0;
    min-height: 0;
  }
  .slot {
    position: relative;
    min-width: 0;
    min-height: 0;
  }
  /* While one is expanded the others step aside, the expanded one taking their room (alone, a share under 1 would
   grow to only that part of it). */
  .hidden {
    display: none;
  }
  /* The conversation shown, the one the user is in. */
  .slot.shown :global(.pane > header h2) {
    color: var(--color-text-primary);
  }
  .slot:not(.shown) :global(.pane > header h2) {
    color: var(--color-text-muted);
  }
  /* A divider between two side by side runs up and down and is dragged across; between two stacked, the other way. */
  .divider {
    flex: none;
    position: relative;
    touch-action: none;
    height: 12px;
    cursor: row-resize;
  }
  .divider.across {
    width: 12px;
    height: auto;
    cursor: col-resize;
  }
  .divider::after {
    content: "";
    position: absolute;
    top: 5px;
    left: 30%;
    right: 30%;
    height: 2px;
    border-radius: 1px;
    background: var(--color-border);
    transition: background 0.12s ease;
  }
  .divider.across::after {
    top: 30%;
    bottom: 30%;
    left: 5px;
    right: auto;
    width: 2px;
    height: auto;
  }
  .divider:hover::after,
  .divider:focus-visible::after {
    background: color-mix(in srgb, var(--glow) 80%, transparent);
  }
  .divider:focus-visible {
    outline: none;
  }
  /* Where a drop goes: the half of the conversation it would take, or a bar at the page's end. */
  [data-drop]::after {
    content: "";
    position: absolute;
    z-index: 2;
    border: 2px dashed color-mix(in srgb, var(--glow) 80%, transparent);
    border-radius: var(--radius-lg, 16px);
    background: color-mix(in srgb, var(--glow) 14%, transparent);
    pointer-events: none;
  }
  [data-drop="left"]::after {
    inset: 0 50% 0 0;
  }
  [data-drop="right"]::after {
    inset: 0 0 0 50%;
  }
  [data-drop="top"]::after {
    inset: 0 0 50% 0;
  }
  [data-drop="bottom"]::after {
    inset: 50% 0 0 0;
  }
  .row.drop-end::after {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    right: 0;
    width: 3px;
    border-radius: 2px;
    background: color-mix(in srgb, var(--glow) 90%, transparent);
    z-index: 1;
  }
  .row.stacked.drop-end::after {
    top: auto;
    left: 0;
    width: auto;
    height: 3px;
  }
</style>
