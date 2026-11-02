<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import { hiddenAsks } from "$lib/chat/hiddenAsks.svelte";
  import ApprovalModal from "./ApprovalModal.svelte";
  import PendingCard from "./PendingCard.svelte";

  // What a run waits for: its dialog, until the user answers it with its buttons. Esc, the scrim and × hide it
  // instead, answering nothing (hiddenAsks, told with `onhide`), and a card shows it again: the conversation's own,
  // above its message box, or over the page (`floating`) where no conversation shows it.
  type Props = { approval: ApprovalRequired; onanswer: (d: Decision) => void; onhide?: () => void; floating?: boolean };
  let { approval, onanswer, onhide, floating = false }: Props = $props();
  const id = $derived(approval.interrupt_id);
  const hidden = $derived(hiddenAsks.has(id));

  function answer(decision: Decision): void {
    hiddenAsks.show(id);
    onanswer(decision);
  }

  function hide(): void {
    hiddenAsks.hide(id);
    onhide?.();
  }
</script>

<!-- Kept while hidden, so what was typed in it (a token, a reason) is still there when it shows again. -->
{#key id}
  <ApprovalModal {approval} onanswer={answer} onhide={hide} {hidden} />
{/key}
{#if hidden && floating}
  <PendingCard {approval} floating onopen={() => hiddenAsks.show(id)} />
{/if}
