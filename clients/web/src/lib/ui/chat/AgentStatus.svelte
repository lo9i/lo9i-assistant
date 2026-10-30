<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import Undo2 from "@lucide/svelte/icons/undo-2";
  import type { Snippet } from "svelte";
  import type { Handoff } from "$lib/api/types";
  import { t } from "$lib/i18n.svelte";

  // In the status bar: the agent this conversation is handed to (/claude), whose replies come from it, not the
  // assistant. Named where the assistant's model is otherwise, so it's plain who answers. `children` (its context)
  // goes between its name and the way back. Its name is in Claude's orange, as the message box's border. The way back
  // is an icon with a short label, its tooltip saying what it does, so it takes little of the bar.
  type Props = { handoff: Handoff; onback: () => void; children?: Snippet };
  let { handoff, onback, children }: Props = $props();
</script>

<div class="agent" title={t("chat.agentIn", { agent: handoff.name, folder: handoff.folder })}>
  <Bot size={13} aria-hidden="true" />
  <span class="name">{handoff.name}</span>
  {@render children?.()}
  <button type="button" class="btn btn--ghost back" title={t("chat.backToAssistantHint", { command: handoff.command })} onclick={onback}
    ><Undo2 size={12} aria-hidden="true" />{t("chat.backToAssistant")}</button
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
  @media (max-width: 680px) {
    .agent {
      flex: 0 1 auto;
      flex-wrap: wrap;
      min-width: 0;
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
</style>
