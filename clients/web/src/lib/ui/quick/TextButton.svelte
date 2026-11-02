<script lang="ts">
  import Keyboard from "@lucide/svelte/icons/keyboard";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import MessageCircleQuestion from "@lucide/svelte/icons/message-circle-question-mark";
  import { hiddenAsks } from "$lib/chat/hiddenAsks.svelte";
  import { finalReply } from "$lib/chat/transcript";
  import { external, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import PendingAsk from "../chat/PendingAsk.svelte";
  import PendingCard from "../chat/PendingCard.svelte";
  import FloatingButton from "./FloatingButton.svelte";
  import QuickPanel from "./QuickPanel.svelte";
  import { quickPanel } from "./openPanel.svelte";

  // A short message to the assistant from any page: written in the inbox, which sends it on to its
  // conversation; the reply shows here.
  const { text: chat } = useDaemon();
  const snapshot = external(chat.subscribe, chat.getSnapshot);
  let draft = $state("");
  let input = $state<HTMLInputElement>();

  const busy = $derived(snapshot.current.busy);
  // What its run waits for, hidden without an answer: the panel shows its card, and the button opens it again.
  const asked = $derived(snapshot.current.approval);
  const askHidden = $derived(!!asked && hiddenAsks.has(asked.interrupt_id));
  const open = $derived(quickPanel.open === "text");
  // The panel opens empty: only what comes after the opening shows, not the last exchange.
  let since = $state(0);
  let wasOpen = false;
  $effect.pre(() => {
    const items = snapshot.current.transcript.items.length;
    if (open && !wasOpen && !busy) since = items;
    wasOpen = open;
  });
  const reply = $derived.by(() => {
    const t = snapshot.current.transcript;
    return finalReply({ ...t, items: t.items.slice(since) });
  });

  // Ready for the next message whenever the panel opens or a reply ends.
  $effect(() => {
    if (open && !busy) input?.focus();
  });

  function press(): void {
    if (asked && askHidden) hiddenAsks.show(asked.interrupt_id);
    else if (busy) void chat.stop();
    else quickPanel.open = open ? null : "text";
  }

  async function send(): Promise<void> {
    const message = draft.trim();
    if (!message || busy) return;
    draft = "";
    await chat.write(message, []);
  }

  function close(): void {
    if (open) quickPanel.open = null;
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === "Enter" && !e.isComposing) {
      e.preventDefault();
      void send();
    }
  }

  function onWindowKeydown(e: KeyboardEvent): void {
    if (e.key === "Escape") close();
  }
</script>

<svelte:window onkeydown={onWindowKeydown} />

{#if open}
  <QuickPanel
    title={t("quick.message")}
    chat={snapshot.current}
    {reply}
    hint={t("quick.messageHint")}
    onstop={() => void chat.stop()}
    onclose={close}
  >
    {#if asked && askHidden}<PendingCard approval={asked} onopen={() => hiddenAsks.show(asked.interrupt_id)} />{/if}
    <input
      bind:this={input}
      bind:value={draft}
      class="input"
      placeholder={t("quick.placeholder")}
      aria-label={t("quick.messageLabel")}
      disabled={busy}
      onkeydown={onKeydown}
    />
  </QuickPanel>
{/if}
<FloatingButton
  label={askHidden ? t("pending.reopen") : busy ? t("quick.stop") : t("quick.type")}
  tone={askHidden ? "waiting" : busy ? "thinking" : ""}
  onclick={press}
>
  {#if askHidden}
    <MessageCircleQuestion size={18} />
  {:else if busy}
    <LoaderCircle size={18} class="spin" />
  {:else}
    <Keyboard size={18} />
  {/if}
</FloatingButton>

{#if asked}
  <PendingAsk approval={asked} onanswer={(d) => chat.answer(d)} onhide={() => (quickPanel.open = "text")} />
{/if}
