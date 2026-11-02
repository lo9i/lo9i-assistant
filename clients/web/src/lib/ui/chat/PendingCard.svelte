<script lang="ts">
  import MessageCircleQuestion from "@lucide/svelte/icons/message-circle-question-mark";
  import type { ApprovalRequired } from "$lib/api/types";
  import { askTitle } from "$lib/chat/asked";
  import { t } from "$lib/i18n.svelte";

  // What the run waits for, hidden by the user without answering it: a line saying so and a button that shows it again.
  // `floating`: over the page, where no conversation shows it (a move asked from the conversation page's columns).
  type Props = { approval: ApprovalRequired; onopen: () => void; floating?: boolean };
  let { approval, onopen, floating = false }: Props = $props();
</script>

<div class="pending" class:floating class:surface--glass={floating} role="status">
  <MessageCircleQuestion size={16} aria-hidden="true" />
  <div class="what">
    <span class="micro-label">{t("pending.waiting")}</span>
    <span class="title" title={askTitle(approval.request)}>{askTitle(approval.request)}</span>
  </div>
  <button class="btn btn--primary btn--sm" onclick={onopen}>{t("pending.open")}</button>
</div>

<style>
  .pending {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 8px 8px 12px;
    border: 1px solid color-mix(in srgb, var(--color-accent) 42%, transparent);
    border-radius: var(--radius-md);
    background: color-mix(in srgb, var(--color-accent) 8%, transparent);
    color: var(--color-accent);
  }
  .floating {
    position: fixed;
    right: 24px;
    bottom: 16px;
    z-index: var(--z-popover);
    width: min(380px, calc(100vw - 48px));
    box-shadow: var(--shadow-popover);
    background: var(--color-bg-page);
  }
  .what {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    color: var(--color-text-primary);
  }
  .title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--font-size-sm);
  }
</style>
