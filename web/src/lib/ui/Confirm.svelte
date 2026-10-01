<script lang="ts">
  import Modal from "./Modal.svelte";

  type Props = { title: string; text: string; action: string; onanswer: (yes: boolean) => void };
  let { title, text, action, onanswer }: Props = $props();
</script>

<Modal {title} width={440} onclose={() => onanswer(false)}>
  <p class="text-label">{text}</p>
  {#snippet footer()}
    <!-- svelte-ignore a11y_autofocus -->
    <button class="btn btn--ghost" onclick={() => onanswer(false)} autofocus>Cancel</button>
    <button class="btn btn--danger" onclick={() => onanswer(true)}>{action}</button>
  {/snippet}
</Modal>
