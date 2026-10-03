<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import Modal from "../Modal.svelte";

  // A question with options from the agent (ask_user): a button per option for one choice,
  // checkboxes and Done for several.
  let { question, onanswer }: { question: ApprovalRequired; onanswer: (d: Decision) => void } = $props();
  const request = $derived(question.request);
  const options = $derived(request.options ?? []);
  let picked = $state<string[]>([]);

  function toggle(option: string, on: boolean): void {
    picked = on ? [...picked, option] : picked.filter((p) => p !== option);
  }
  // In the order of the options, whatever order they were ticked in.
  const done = () => onanswer({ choices: options.filter((o) => picked.includes(o)) });
  const skip = () => onanswer({ choices: null });
</script>

<Modal title={request.question ?? "Pick one"} description={request.multiple ? "Pick any, then Done." : undefined} onclose={skip}>
  <div class="options">
    {#each options as option (option)}
      {#if request.multiple}
        <label class="check">
          <input type="checkbox" checked={picked.includes(option)} onchange={(e) => toggle(option, e.currentTarget.checked)} />
          {option}
        </label>
      {:else}
        <button class="btn btn--neutral option" onclick={() => onanswer({ choices: [option] })}>{option}</button>
      {/if}
    {/each}
  </div>
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={skip}>Skip</button>
    {#if request.multiple}
      <button class="btn btn--primary" onclick={done}>Done</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .options {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--font-size-sm);
    cursor: pointer;
  }
  .option {
    justify-content: flex-start;
  }
</style>
