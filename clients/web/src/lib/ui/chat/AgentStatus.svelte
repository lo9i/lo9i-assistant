<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import Undo2 from "@lucide/svelte/icons/undo-2";
  import type { Snippet } from "svelte";
  import type { Handoff } from "$lib/api/types";
  import { clock } from "$lib/clock.svelte";
  import { duration } from "$lib/duration";
  import { t } from "$lib/i18n.svelte";

  // In the status bar: the agent this conversation is handed to (/claude), whose replies come from it, not the
  // assistant. Named where the assistant's model is otherwise, so it's plain who answers; while it works, a spinner
  // and for how long go beside its name, no words: the spinner says it's working. `children` (its context) goes between its name and the way
  // back. Its name is in Claude's orange, as the message box's border. The way back is an icon with a short label,
  // its tooltip saying what it does, so it takes little of the bar.
  type Props = {
    handoff: Handoff;
    onback: () => void;
    /** When its task started, while it works on the last message; null while it waits. */
    since?: string | null;
    children?: Snippet;
  };
  let { handoff, onback, since = null, children }: Props = $props();
  const time = clock();
</script>

<div class="agent" title={t("chat.agentIn", { agent: handoff.name, folder: handoff.folder })}>
  {#if since}
    <LoaderCircle size={13} class="spin" aria-label={t("nav.working")} />
  {:else}
    <Bot size={13} aria-hidden="true" />
  {/if}
  <span class="name">{handoff.name}</span>
  {#if since}<span class="working">{duration(since, time.now)}</span>{/if}
  {@render children?.()}
  <button
    type="button"
    class="btn btn--ghost back"
    aria-label={t("chat.backToAssistant")}
    title={t("chat.backToAssistantHint", { command: handoff.command })}
    onclick={onback}><Undo2 size={12} aria-hidden="true" /><span class="back-label">{t("chat.backToAssistant")}</span></button
  >
</div>

<style>
  /* Its controls keep their size; the status bar's other items give way. */
  .agent {
    display: flex;
    flex: none;
    align-items: center;
    gap: 6px;
  }
  /* Where the status bar is too narrow for its controls (StatusBar's container), they wrap too. */
  @container status-bar (max-width: 640px) {
    .agent {
      flex: 0 1 auto;
      flex-wrap: wrap;
      min-width: 0;
    }
    /* With little room, the way back is its icon alone; its tooltip says where it goes. */
    .back-label {
      display: none;
    }
  }
  .back {
    gap: 4px;
    padding: 3px 6px;
    font-size: 11px;
    font-weight: 500;
  }
  .name {
    cursor: default;
    color: var(--color-agent);
  }
  .agent :global(.spin) {
    flex: none;
    color: var(--color-agent);
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .agent :global(.spin) {
      animation: none;
    }
  }
</style>
