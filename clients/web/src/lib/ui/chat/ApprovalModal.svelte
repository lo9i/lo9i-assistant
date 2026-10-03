<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import Modal from "../Modal.svelte";
  import QuestionModal from "./QuestionModal.svelte";

  // What the run waits for: an approval, or a question with options.
  let { approval, onanswer }: { approval: ApprovalRequired; onanswer: (d: Decision) => void } = $props();
  let reason = $state("");
  const request = $derived(approval.request);
  const reject = () => onanswer({ approved: false, reason: reason.trim() || null });
</script>

{#if request.kind === "question"}
  <QuestionModal question={approval} {onanswer} />
{:else}
  <Modal title="Approve {String(request.tool ?? 'this action')}?" description={request.reason ? String(request.reason) : undefined}>
    <pre>{request.command ?? JSON.stringify(request, null, 2)}</pre>
    <input
      class="input"
      placeholder="Reason, if you reject (optional)"
      bind:value={reason}
      onkeydown={(e) => e.key === "Enter" && reject()}
    />
    {#snippet footer()}
      <button class="btn btn--danger" onclick={reject}>Reject</button>
      <!-- svelte-ignore a11y_autofocus -->
      <button class="btn btn--primary" onclick={() => onanswer({ approved: true, reason: null })} autofocus>Approve</button>
    {/snippet}
  </Modal>
{/if}
