<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import Modal from "../Modal.svelte";

  // The agent suggests moving a focused task out of home (suggest_side_conversation), to a new side
  // conversation or one that exists. On yes, the chat goes there once the reply ends and sends the brief.
  let { suggestion, onanswer }: { suggestion: ApprovalRequired; onanswer: (d: Decision) => void } = $props();
  const request = $derived(suggestion.request);
  const continues = $derived(Boolean(request.thread_id));
  const stay = () => onanswer({ moved: false });
</script>

<Modal
  title={continues ? "Continue in your side conversation?" : "Move to a side conversation?"}
  description={String(request.title ?? "")}
  onclose={stay}
>
  <p class="text-meta">
    {continues ? "This goes on there" : "This goes on in a conversation of its own"}, starting with this brief, so home stays light.
  </p>
  <pre>{request.brief}</pre>
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={stay}>Keep it here</button>
    <!-- svelte-ignore a11y_autofocus -->
    <button class="btn btn--primary" onclick={() => onanswer({ moved: true })} autofocus>Move</button>
  {/snippet}
</Modal>
