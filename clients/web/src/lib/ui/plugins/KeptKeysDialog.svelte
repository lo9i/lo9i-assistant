<script lang="ts">
  import { useDaemon } from "$lib/daemon.svelte";
  import { describeKept, keptKeys } from "$lib/keptKeys.svelte";
  import Modal from "../Modal.svelte";

  // Asked after a plugin is removed: its keys stay encrypted, for installing it again, unless the user
  // deletes them. Closing it keeps them.
  const { client, notices } = useDaemon();

  async function answer(remove: boolean): Promise<void> {
    const kept = keptKeys.pending;
    keptKeys.pending = null;
    if (!kept || !remove) return;
    try {
      await client.repositories.forgetKeys(kept);
      notices.notify(`Deleted the keys of ${kept.plugin}.`);
    } catch (e) {
      notices.report(e);
    }
  }
</script>

{#if keptKeys.pending}
  <Modal title="Keep the keys of {keptKeys.pending.plugin}?" width={460} onclose={() => answer(false)}>
    <p class="text-label">
      {describeKept(keptKeys.pending)}
      {keptKeys.pending.keys.length + (keptKeys.pending.repository ? 1 : 0) > 1 ? "are" : "is"} kept encrypted on this computer. Kept keys are
      used when you install it again, so you don't type them again.
    </p>
    {#snippet footer()}
      <button class="btn btn--danger" onclick={() => answer(true)}>Delete</button>
      <!-- svelte-ignore a11y_autofocus -->
      <button class="btn btn--primary" onclick={() => answer(false)} autofocus>Keep</button>
    {/snippet}
  </Modal>
{/if}
