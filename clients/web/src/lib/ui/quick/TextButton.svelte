<script lang="ts">
  import Keyboard from "@lucide/svelte/icons/keyboard";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import { finalReply } from "$lib/chat/transcript";
  import { external, useDaemon } from "$lib/daemon.svelte";
  import ApprovalModal from "../chat/ApprovalModal.svelte";
  import FloatingButton from "./FloatingButton.svelte";
  import QuickPanel from "./QuickPanel.svelte";
  import { quickPanel } from "./openPanel.svelte";

  // A short message to the assistant from any page: written in the inbox, which sends it on to its
  // conversation; the reply shows here.
  // `docked`: in a chat's status bar (QuickButtons).
  let { docked = false }: { docked?: boolean } = $props();
  const { text: chat } = useDaemon();
  const snapshot = external(chat.subscribe, chat.getSnapshot);
  let draft = $state("");
  let input = $state<HTMLInputElement>();

  const busy = $derived(snapshot.current.busy);
  const reply = $derived(finalReply(snapshot.current.transcript));
  const open = $derived(quickPanel.open === "text");

  // Ready for the next message whenever the panel opens or a reply ends.
  $effect(() => {
    if (open && !busy) input?.focus();
  });

  function press(): void {
    if (busy) void chat.stop();
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
    title="Message"
    chat={snapshot.current}
    {reply}
    hint="Ask for something; it goes to the right conversation."
    onstop={() => void chat.stop()}
    onclose={close}
    {docked}
  >
    <input
      bind:this={input}
      bind:value={draft}
      class="input"
      placeholder="Type a short message"
      aria-label="Message to the assistant"
      disabled={busy}
      onkeydown={onKeydown}
    />
  </QuickPanel>
{/if}
<FloatingButton label={busy ? "Stop" : "Type to the assistant"} tone={busy ? "thinking" : ""} onclick={press}>
  {#if busy}
    <LoaderCircle size={12} class="spin" />
  {:else}
    <Keyboard size={12} />
  {/if}
</FloatingButton>

{#if snapshot.current.approval}
  <ApprovalModal approval={snapshot.current.approval} onanswer={(d) => chat.answer(d)} />
{/if}
