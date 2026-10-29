<script lang="ts">
  import type { Snippet } from "svelte";
  import X from "@lucide/svelte/icons/x";
  import { t } from "$lib/i18n.svelte";

  type Props = {
    title: string;
    description?: string;
    width?: number;
    /** Esc, the scrim and × close it when given. */
    onclose?: () => void;
    children: Snippet;
    footer?: Snippet;
  };
  let { title, description, width = 520, onclose, children, footer }: Props = $props();

  // Shown from the page's body: a card with a backdrop filter (the glass surfaces) would otherwise hold
  // the fixed scrim inside itself, so a dialog opened from a card never showed.
  function portal(node: HTMLElement): { destroy: () => void } {
    document.body.appendChild(node);
    return { destroy: () => node.remove() };
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === "Escape" && onclose) onclose();
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="scrim" role="presentation" onclick={onclose} use:portal>
  <div
    class="modal"
    style:max-width="{width}px"
    role="dialog"
    aria-modal="true"
    aria-label={title}
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <header>
      <div>
        <h2>{title}</h2>
        {#if description}<p class="text-label">{description}</p>{/if}
      </div>
      {#if onclose}
        <button class="btn btn--icon" style="--btn-icon-size: 32px" aria-label={t("common.close")} onclick={onclose}>
          <X size={18} />
        </button>
      {/if}
    </header>
    <div class="body">{@render children()}</div>
    {#if footer}<footer>{@render footer()}</footer>{/if}
  </div>
</div>

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    display: grid;
    place-items: center;
    padding: 24px;
    background: var(--scrim-bg);
    backdrop-filter: var(--scrim-blur);
  }
  .modal {
    width: 100%;
    max-height: min(86vh, 760px);
    display: flex;
    flex-direction: column;
    border-radius: var(--radius-lg);
    border: 1px solid var(--surface-glass-border);
    background: var(--surface-modal-bg);
    backdrop-filter: var(--surface-glass-blur);
    box-shadow: var(--shadow-modal);
    animation: pop 0.14s ease;
  }
  @keyframes pop {
    from {
      transform: scale(0.97);
      opacity: 0;
    }
  }
  header {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    padding: 24px 24px 16px;
    border-bottom: 1px solid var(--color-border);
  }
  h2 {
    margin: 0 0 4px;
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  .body {
    padding: 24px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  footer {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 16px 24px;
    border-top: 1px solid var(--color-border);
  }
</style>
