<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import type { ConversationModels } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { modelChoices } from "$lib/chat/models";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";

  // In the status bar: the model the conversation answers with, and a menu to change it, also before its first message.
  // The models are asked for when the menu opens. A change in a conversation with messages leaves a note there (the
  // daemon's `conversation_model` event shows it); not while a reply runs. Hidden when the model can't be loaded.
  let { threadId, running }: { threadId: string; running: boolean } = $props();

  const { client, notices } = useDaemon();
  const model = resource((c) => c.conversations.model(threadId), ["conversation_model", "settings"]);
  let open = $state(false);
  let offered = $state<ConversationModels | null>(null);
  let failed = $state("");
  let root = $state<HTMLElement>();
  const choices = $derived(offered ? modelChoices(offered) : []);

  async function toggle(): Promise<void> {
    open = !open;
    if (!open) return;
    failed = "";
    try {
      offered = await client.conversations.models();
    } catch (e) {
      failed = describe(e);
    }
  }

  async function pick(id: string): Promise<void> {
    open = false;
    if (id === (model.data?.main ? "" : model.data?.model)) return;
    try {
      await client.conversations.setModel(threadId, id);
    } catch (e) {
      notices.report(e);
    }
  }

  /** A click anywhere else, or Escape, closes the menu. */
  function outside(e: MouseEvent): void {
    if (open && root && !root.contains(e.target as Node)) open = false;
  }
</script>

<svelte:window onclick={outside} onkeydown={(e) => e.key === "Escape" && (open = false)} />

{#if model.data && !model.error}
  {@const current = model.data}
  <div class="picker" bind:this={root}>
    <button
      type="button"
      class="trigger"
      aria-haspopup="listbox"
      aria-expanded={open}
      disabled={running}
      title={running ? t("chat.modelBusy") : t("chat.modelPick")}
      onclick={toggle}><span class="name">{current.name}</span><ChevronDown size={12} aria-hidden="true" /></button
    >
    {#if open}
      <div class="menu surface--popover" role="listbox" aria-label={t("chat.modelPick")}>
        {#if failed}
          <p class="note">{failed}</p>
        {:else if !offered}
          <p class="note">{t("chat.modelsLoading")}</p>
        {:else}
          {#each choices as choice (choice.id)}
            {@const picked = choice.id === "" ? current.main : !current.main && choice.id === current.model}
            <button type="button" class="choice" role="option" aria-selected={picked} onclick={() => pick(choice.id)}>
              <span class="check"
                >{#if picked}<Check size={12} />{/if}</span
              >
              <span class="label">{choice.id === "" ? t("chat.modelMain", { model: choice.name }) : choice.name}</span>
            </button>
          {/each}
          <p class="note">{t("chat.modelHint")}</p>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .picker {
    position: relative;
    min-width: 0;
  }
  .trigger {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    max-width: 100%;
    padding: 0;
    border: none;
    background: none;
    color: #e5b931;
    font: inherit;
    cursor: pointer;
  }
  .trigger:disabled {
    cursor: default;
    opacity: 0.7;
  }
  .trigger:hover:not(:disabled) .name {
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* Above the status bar, which sits at the bottom of the chat. */
  .menu {
    position: absolute;
    bottom: calc(100% + 6px);
    left: -8px;
    z-index: 30;
    display: flex;
    flex-direction: column;
    width: max-content;
    min-width: 200px;
    max-width: min(340px, calc(100vw - 24px));
    max-height: 50dvh;
    overflow-y: auto;
    padding: 4px;
    white-space: normal;
  }
  .choice {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    border: none;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .choice:hover,
  .choice:focus-visible {
    background: color-mix(in srgb, var(--color-accent) 10%, transparent);
  }
  .check {
    display: inline-grid;
    flex: none;
    width: 12px;
    color: var(--color-accent);
  }
  .note {
    margin: 0;
    padding: 6px 8px;
    color: var(--color-text-muted);
  }
</style>
