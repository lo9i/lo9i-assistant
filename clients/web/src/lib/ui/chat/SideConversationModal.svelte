<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import Modal from "../Modal.svelte";

  // The agent suggests moving a focused task out of home (suggest_side_conversation). On yes, the
  // chat starts a side conversation once the reply ends and sends the brief there.
  let { suggestion, onanswer }: { suggestion: ApprovalRequired; onanswer: (d: Decision) => void } = $props();
  const request = $derived(suggestion.request);
  const stay = () => onanswer({ moved: false });
</script>

<Modal title="Move to a side conversation?" description={String(request.title ?? "")} onclose={stay}>
  <p class="text-meta">This goes on in a conversation of its own, starting with this brief, so home stays light.</p>
  <pre>{request.brief}</pre>
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={stay}>Keep it here</button>
    <!-- svelte-ignore a11y_autofocus -->
    <button class="btn btn--primary" onclick={() => onanswer({ moved: true })} autofocus>Move</button>
  {/snippet}
</Modal>
