<script lang="ts">
  import CircleAlert from "@lucide/svelte/icons/circle-alert";
  import Info from "@lucide/svelte/icons/info";
  import TriangleAlert from "@lucide/svelte/icons/triangle-alert";
  import X from "@lucide/svelte/icons/x";
  import { external } from "$lib/daemon.svelte";
  import type { Notice, NoticeBoard } from "$lib/notices";

  const SHOW_MS = 8000;
  const ICONS = { info: Info, warning: TriangleAlert, error: CircleAlert };

  let { notices }: { notices: NoticeBoard } = $props();

  // svelte-ignore state_referenced_locally
  const shown = external(notices.subscribe, notices.getSnapshot);

  function autoDismiss(_: HTMLElement, notice: Notice) {
    const timer = setTimeout(() => notices.dismiss(notice.id), SHOW_MS);
    return { destroy: () => clearTimeout(timer) };
  }
</script>

<div class="toasts" aria-live="polite">
  {#each shown.current as notice (notice.id)}
    {@const Icon = ICONS[notice.level]}
    <div class="toast {notice.level}" use:autoDismiss={notice}>
      <span class="icon"><Icon size={18} /></span>
      <p>{notice.text}</p>
      <button aria-label="Dismiss" onclick={() => notices.dismiss(notice.id)}><X size={16} /></button>
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    right: 24px;
    /* Above the voice button (VoiceButton.svelte). */
    bottom: 96px;
    z-index: var(--z-toast);
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: min(360px, calc(100vw - 48px));
  }
  .toast {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 12px;
    align-items: start;
    padding: 16px;
    border-radius: var(--radius-md);
    border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
    background: color-mix(in srgb, var(--color-bg-card) 92%, transparent);
    backdrop-filter: blur(12px);
    box-shadow: 0 12px 40px color-mix(in srgb, #000 35%, transparent);
    animation: enter 0.2s ease;
  }
  @keyframes enter {
    from {
      transform: translateY(8px);
      opacity: 0;
    }
  }
  .icon {
    color: var(--color-accent);
  }
  .warning {
    border-color: color-mix(in srgb, var(--color-warn) 38%, var(--color-border));
  }
  .warning .icon {
    color: var(--color-warn);
  }
  .error {
    border-color: color-mix(in srgb, var(--color-danger) 40%, var(--color-border));
  }
  .error .icon {
    color: var(--color-danger);
  }
  p {
    margin: 0;
    line-height: 1.45;
  }
  button {
    border: 0;
    background: none;
    color: var(--color-text-faint);
    cursor: pointer;
    padding: 0;
  }
</style>
