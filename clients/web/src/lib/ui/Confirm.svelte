<script lang="ts">
  import Modal from "./Modal.svelte";

  // `option`: a checkbox, unchecked at first, whose state comes with the answer.
  type Props = { title: string; text: string; action: string; option?: string; onanswer: (yes: boolean, option: boolean) => void };
  let { title, text, action, option, onanswer }: Props = $props();
  let checked = $state(false);
</script>

<Modal {title} width={440} onclose={() => onanswer(false, false)}>
  <p class="text-label">{text}</p>
  {#if option}
    <label class="check"><input type="checkbox" bind:checked />{option}</label>
  {/if}
  {#snippet footer()}
    <!-- svelte-ignore a11y_autofocus -->
    <button class="btn btn--ghost" onclick={() => onanswer(false, false)} autofocus>Cancel</button>
    <button class="btn btn--danger" onclick={() => onanswer(true, checked)}>{action}</button>
  {/snippet}
</Modal>

<style>
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
    font-size: var(--font-size-sm);
    cursor: pointer;
  }
</style>
