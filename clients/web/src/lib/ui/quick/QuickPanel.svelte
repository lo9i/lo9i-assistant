<script lang="ts">
  import ArrowUpRight from "@lucide/svelte/icons/arrow-up-right";
  import X from "@lucide/svelte/icons/x";
  import type { Snippet } from "svelte";
  import type { ChatSnapshot } from "$lib/chat/controller";
  import { useDaemon } from "$lib/daemon.svelte";
  import { openConversation } from "../openConversation";

  // The panel above the quick buttons: what was asked (`children`), the reply, and the conversation the
  // inbox sent the message on to, to open in Chat. `docked`: the buttons are in a row while a chat is
  // shown, lower than when they're stacked.
  let {
    title,
    chat,
    reply,
    hint = "",
    onstop,
    onclose,
    docked = false,
    children,
  }: {
    title: string;
    chat: ChatSnapshot;
    reply: string;
    hint?: string;
    onstop: () => void;
    onclose: () => void;
    docked?: boolean;
    children?: Snippet;
  } = $props();

  const { chats, notices } = useDaemon();
  const inInbox = $derived(chat.threadId === chat.inboxId);

  async function open(): Promise<void> {
    onclose();
    await openConversation(chats, notices, chat.threadId, chat.inboxId);
  }
</script>

<section class="bubble surface--glass" class:docked aria-live="polite">
  <header>
    <span class="micro-label">{title}</span>
    <button class="icon" aria-label="Close" title="Close" onclick={onclose}><X size={14} /></button>
  </header>
  {@render children?.()}
  {#if chat.busy}
    <p class="status">
      {reply ? "Replying…" : "Thinking…"}
      <button class="btn btn--ghost btn--sm" onclick={onstop}>Stop</button>
    </p>
  {/if}
  {#if reply}
    <p class="reply">{reply}</p>
    {#if !chat.busy}
      <button class="btn btn--ghost btn--sm open" onclick={open}>
        {inInbox ? "Open the inbox" : "Open the conversation"}
        <ArrowUpRight size={12} />
      </button>
    {/if}
  {:else if !chat.busy && hint}
    <p class="status">{hint}</p>
  {/if}
</section>

<style>
  /* Above the buttons, in the same corner: two one above the other, or a row while a chat is shown. */
  .bubble {
    position: fixed;
    right: 10px;
    bottom: 88px;
    z-index: var(--z-popover);
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: min(360px, calc(100vw - 48px));
    max-height: 50vh;
    overflow-y: auto;
    padding: 12px 16px 16px;
    box-shadow: var(--shadow-popover);
  }
  .bubble.docked {
    bottom: 51px;
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
