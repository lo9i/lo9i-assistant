<script lang="ts">
  import { t } from "$lib/i18n.svelte";
  import { panelWidths } from "$lib/panelWidths.svelte";

  // Between the chat (or the panel before) and a side panel right after it, in ChatPanel's row: dragging it (mouse,
  // touch or pen) or its arrow keys set the panel's width, kept in panelWidths under `name`; a double-click gives the
  // panel back its own. The room comes from the chat, which keeps CHAT_MIN. While it's dragged a cover over the page
  // takes the pointer, so a frame or anything that captures it under the pointer doesn't stop the drag.
  type Props = { name: string };
  let { name }: Props = $props();
  const PANEL_MIN = 260;
  const CHAT_MIN = 320;
  // Moved from the keyboard, as a share of the row.
  const STEP = 0.02;
  const share = $derived(panelWidths.get(name));
  const dragging = $derived(panelWidths.dragging === name);

  /** The width of the panel after `divider` and the share of the row a width in pixels makes, kept within bounds. */
  function measure(divider: HTMLElement): { width: number; share: (px: number) => number } | null {
    const panel = divider.nextElementSibling;
    const row = divider.parentElement;
    const chat = row?.firstElementChild;
    if (!(panel instanceof HTMLElement) || !row || !chat || row.clientWidth === 0) return null;
    const width = panel.getBoundingClientRect().width;
    const most = Math.max(PANEL_MIN, width + chat.getBoundingClientRect().width - CHAT_MIN);
    return { width, share: (px) => Math.min(Math.max(px, PANEL_MIN), most) / row.clientWidth };
  }

  function start(e: PointerEvent): void {
    if (e.button !== 0) return;
    const divider = e.currentTarget as HTMLElement;
    const bounds = measure(divider);
    if (!bounds) return;
    // No text selected on the way.
    e.preventDefault();
    divider.setPointerCapture(e.pointerId);
    panelWidths.dragging = name;
    const from = e.clientX;
    // The panel is on the divider's right: moving left widens it.
    const move = (m: PointerEvent) => panelWidths.set(name, bounds.share(bounds.width - (m.clientX - from)));
    const end = () => {
      divider.removeEventListener("pointermove", move);
      divider.removeEventListener("pointerup", end);
      divider.removeEventListener("pointercancel", end);
      panelWidths.dragging = null;
      panelWidths.save();
    };
    divider.addEventListener("pointermove", move);
    divider.addEventListener("pointerup", end);
    divider.addEventListener("pointercancel", end);
  }

  function key(e: KeyboardEvent): void {
    const steps: Record<string, number> = { ArrowLeft: STEP, ArrowRight: -STEP };
    if (!(e.key in steps)) return;
    const divider = e.currentTarget as HTMLElement;
    const bounds = measure(divider);
    if (!bounds) return;
    e.preventDefault();
    const row = divider.parentElement?.clientWidth ?? 0;
    panelWidths.set(name, bounds.share(bounds.width + steps[e.key] * row));
    panelWidths.save();
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div
  class="divider"
  class:dragging
  role="separator"
  aria-orientation="vertical"
  aria-label={t("chat.resizePanel")}
  aria-valuenow={share === null ? undefined : Math.round(share * 100)}
  tabindex="0"
  title={t("chat.resizePanel")}
  onpointerdown={start}
  onkeydown={key}
  ondblclick={() => panelWidths.reset(name)}
></div>
{#if dragging}<div class="cover" aria-hidden="true"></div>{/if}

<style>
  /* In the row's 12px gap: as wide as it, the margins giving it back so the chat and the panel stay as far apart. */
  .divider {
    flex: none;
    position: relative;
    width: 12px;
    margin-inline: -12px;
    touch-action: none;
    cursor: col-resize;
  }
  /* A thin line, as the conversation page's dividers; it lights up under the pointer and while dragged. */
  .divider::after {
    content: "";
    position: absolute;
    top: 30%;
    bottom: 30%;
    left: 5px;
    width: 2px;
    border-radius: 1px;
    background: color-mix(in srgb, var(--color-border) 70%, transparent);
    transition: background 0.12s ease;
  }
  .divider:hover::after,
  .divider:focus-visible::after,
  .divider.dragging::after {
    background: color-mix(in srgb, var(--glow) 80%, transparent);
  }
  .divider:focus-visible {
    outline: none;
  }
  .cover {
    position: fixed;
    inset: 0;
    z-index: 9999;
    cursor: col-resize;
    user-select: none;
  }
  /* Narrow, the panels cover the chat instead of sitting beside it: nothing to divide. */
  @media (max-width: 900px) {
    .divider {
      display: none;
    }
  }
</style>
