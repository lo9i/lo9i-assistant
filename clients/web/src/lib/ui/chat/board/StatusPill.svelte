<script lang="ts">
  import type { CardStatus } from "$lib/chat/cards";
  import { t } from "$lib/i18n.svelte";

  let { status }: { status: CardStatus } = $props();
</script>

{#if status === "waiting"}
  <span class="pill pill--warn" role="status">{t("board.waiting")}</span>
{:else if status === "working"}
  <span class="pill pill--accent" role="status"><span class="pulse" aria-hidden="true"></span>{t("board.working")}</span>
{:else}
  <span class="pill idle" role="status">{t("board.idle")}</span>
{/if}

<style>
  .idle {
    color: var(--color-text-faint);
  }
  .pulse {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    animation: pulse 1.2s ease-in-out infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.3;
    }
  }
</style>
