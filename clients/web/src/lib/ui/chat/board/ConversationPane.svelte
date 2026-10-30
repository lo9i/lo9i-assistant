<script lang="ts">
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import GripVertical from "@lucide/svelte/icons/grip-vertical";
  import Maximize2 from "@lucide/svelte/icons/maximize-2";
  import Minimize2 from "@lucide/svelte/icons/minimize-2";
  import X from "@lucide/svelte/icons/x";
  import type { CardStatus } from "$lib/chat/cards";
  import type { ChatController } from "$lib/chat/controller";
  import { t } from "$lib/i18n.svelte";
  import PinToHome from "../../PinToHome.svelte";
  import ChatPanel from "../ChatPanel.svelte";
  import StatusPill from "./StatusPill.svelte";

  type Props = {
    chat: ChatController;
    title: string;
    status: CardStatus;
    /** Expanded to the whole of the page's room for conversations, the others out of the way; where they go is the
     * page's. Here it only changes what its header offers. */
    maximized: boolean;
    /** Cmd+F finds in it: the pane the user is in. */
    findable: boolean;
    onmaximize: () => void;
    /** Given where it isn't Chat's conversation page already (a card full screen): opening it there. */
    onopen?: () => void;
    /** /clear in it: a new conversation in its place. */
    onclear: () => void;
    /** It's pinned to Home. */
    pinned: boolean;
    onpin: () => void;
    /** Given for a pane side by side: closing it, and its header dragging it. */
    onclose?: () => void;
    ondragstart?: (e: DragEvent) => void;
  };
  let { chat, title, status, maximized, findable, onmaximize, onopen, onclear, pinned, onpin, onclose, ondragstart }: Props = $props();
</script>

<section class="pane" class:maximized aria-label={title}>
  <!-- Dragging is the mouse's way to reorder; closing and opening beside again does it from the keyboard. -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <header draggable={ondragstart !== undefined && !maximized} {ondragstart} class:movable={ondragstart && !maximized}>
    {#if ondragstart && !maximized}<span class="grip" aria-hidden="true" title={t("board.move")}><GripVertical size={14} /></span>{/if}
    <h2 class="text-heading">{title}</h2>
    <StatusPill {status} />
    <span class="spacer"></span>
    <PinToHome {pinned} ontoggle={onpin} />
    {#if onopen}
      <button class="btn btn--ghost btn--icon btn--sm" aria-label={t("board.openFull")} title={t("board.openFull")} onclick={onopen}
        ><ExternalLink size={14} /></button
      >
    {/if}
    <button
      class="btn btn--ghost btn--icon btn--sm"
      aria-label={maximized ? t("board.restore") : t("board.maximize")}
      title={maximized ? t("board.restore") : t("board.maximize")}
      aria-pressed={maximized}
      onclick={onmaximize}
    >
      {#if maximized}<Minimize2 size={14} />{:else}<Maximize2 size={14} />{/if}
    </button>
    {#if onclose && !maximized}
      <button class="btn btn--ghost btn--icon btn--sm" aria-label={t("board.closePane")} title={t("board.closePane")} onclick={onclose}
        ><X size={14} /></button
      >
    {/if}
  </header>
  <div class="body"><ChatPanel {chat} asksMoves={false} {findable} {onclear} /></div>
</section>

<style>
  .pane {
    display: flex;
    flex-direction: column;
    gap: 6px;
    height: 100%;
    min-width: 0;
    min-height: 0;
  }
  header {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    padding: 0 4px;
  }
  header.movable {
    cursor: grab;
  }
  header.movable:active {
    cursor: grabbing;
  }
  .grip {
    display: flex;
    flex: none;
    color: var(--color-text-faint);
  }
  h2 {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .spacer {
    flex: 1;
  }
  .body {
    flex: 1;
    min-height: 0;
  }
</style>
