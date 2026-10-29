<script lang="ts">
  import ArrowUpRight from "@lucide/svelte/icons/arrow-up-right";
  import X from "@lucide/svelte/icons/x";
  import type { Snippet } from "svelte";
  import type { ChatSnapshot } from "$lib/chat/controller";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { openConversation } from "../openConversation";

  // The panel above the quick buttons: what was asked (`children`), the reply, and the conversation the
  // inbox sent the message on to, to open in Chat; a quick answer in the inbox has none to open.
  let {
    title,
    chat,
    reply,
    hint = "",
    onstop,
    onclose,
    children,
  }: {
    title: string;
    chat: ChatSnapshot;
    reply: string;
    hint?: string;
    onstop: () => void;
    onclose: () => void;
    children?: Snippet;
  } = $props();

  const { chats, notices } = useDaemon();
  const inInbox = $derived(chat.threadId === chat.inboxId);

  async function open(): Promise<void> {
    onclose();
    await openConversation(chats, notices, chat.threadId);
  }
</script>

<section class="bubble surface--glass" aria-live="polite">
  <header>
    <span class="micro-label">{title}</span>
    <button class="icon" aria-label={t("common.close")} title={t("common.close")} onclick={onclose}><X size={14} /></button>
  </header>
  {@render children?.()}
  {#if chat.busy}
    <p class="status">
      {reply ? t("quick.replying") : t("quick.thinking")}
      <button class="btn btn--ghost btn--sm" onclick={onstop}>{t("quick.stop")}</button>
    </p>
  {/if}
  {#if reply}
    <p class="reply">{reply}</p>
    {#if !chat.busy && !inInbox}
      <button class="btn btn--ghost btn--sm open" onclick={open}>
        {t("quick.openConversation")}
        <ArrowUpRight size={12} />
      </button>
    {/if}
  {:else if !chat.busy && hint}
    <p class="status">{hint}</p>
  {/if}
</section>

<style>
  /* Beside the sidebar's bottom bar, where its buttons are. */
  .bubble {
    position: fixed;
    left: calc(var(--sidebar-rail, 220px) + 24px);
    bottom: 16px;
    z-index: var(--z-popover);
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: min(360px, calc(100vw - 48px));
    max-height: 50vh;
    overflow-y: auto;
    padding: 12px 16px 16px;
    box-shadow: var(--shadow-popover);
    /* Solid, so the page behind doesn't bleed through. */
    background: var(--color-bg-page);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .icon {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .icon:hover {
    background: var(--color-bg-hover-ghost);
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .status {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    color: var(--color-text-muted);
  }
  .reply {
    white-space: pre-wrap;
  }
  .open {
    align-self: flex-start;
    gap: 4px;
  }
</style>
