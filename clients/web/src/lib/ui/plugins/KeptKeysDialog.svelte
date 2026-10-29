<script lang="ts">
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
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
      notices.notify(t("keptKeys.deletedKeys", { plugin: kept.plugin }));
    } catch (e) {
      notices.report(e);
    }
  }
</script>

{#if keptKeys.pending}
  <Modal title={t("keptKeys.keepTitle", { plugin: keptKeys.pending.plugin })} width={460} onclose={() => answer(false)}>
    <p class="text-label">
      {t("keptKeys.keptText", {
        what: describeKept(keptKeys.pending),
        count: keptKeys.pending.keys.length + (keptKeys.pending.repository ? 1 : 0),
      })}
    </p>
    {#snippet footer()}
      <button class="btn btn--danger" onclick={() => answer(true)}>{t("common.delete")}</button>
      <!-- svelte-ignore a11y_autofocus -->
      <button class="btn btn--primary" onclick={() => answer(false)} autofocus>{t("keptKeys.keep")}</button>
    {/snippet}
  </Modal>
{/if}
