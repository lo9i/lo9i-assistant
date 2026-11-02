<script lang="ts">
  // A restart or stop the daemon accepted, until it's back: from the Assistant card's buttons, an update the Host card
  // installed, another tab, or before this page loaded. The page waits for it to come back.
  import { LoaderCircle } from "@lucide/svelte";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { answerable, coming, endingText, waitingText, type Coming } from "$lib/shutdown";
  import Modal from "../Modal.svelte";

  // Set by the card that asked for it at once, before the daemon's `ending` event comes. While it waits, it can be
  // taken back (unless an update was installed), or made to go ahead now by cancelling the runs it waits for.
  let { ending = $bindable(null) }: { ending?: Coming | null } = $props();
  const { client, hub, notices } = useDaemon();
  // Cancel or Now was pressed and the daemon hasn't answered yet.
  let answering = $state(false);

  $effect(() => {
    void pending();
    return hub.on(["ending"], (data) => (ending = coming(data)));
  });
  // How many runs it still waits for; once none, it's going ahead and the count stays.
  $effect(() => hub.on(["run_finished"], () => void pending()));

  // The events stream reconnects on its own; once it does, the daemon is back, maybe with a new web build.
  $effect(() => {
    if (ending) return hub.onReconnect(() => location.reload());
  });

  /** What else it waits for (an update being installed), and whether it can be taken back. */
  export async function pending(): Promise<void> {
    try {
      const found = coming(await client.system.ending());
      if (found) ending = found;
    } catch (e) {
      notices.report(e);
    }
  }

  async function takeBack(): Promise<void> {
    await whileAnswering(async () => {
      await client.system.takeBackEnding();
      ending = null;
    });
  }

  async function now(): Promise<void> {
    await whileAnswering(() => client.system.endNow());
  }

  async function whileAnswering(action: () => Promise<unknown>): Promise<void> {
    answering = true;
    try {
      await action();
    } catch (e) {
      notices.report(e);
    } finally {
      answering = false;
    }
  }
</script>

{#if ending}
  <!-- No way to close it: the page has nothing to show until the daemon is back, and then it reloads. While it
       waits for runs, Cancel takes it back and Now cancels them. -->
  <Modal title={ending.ending === "restart" ? t("host.restarting") : t("host.stopping")} width={440}>
    {@const can = answerable(ending)}
    <p class="text-label">{endingText(ending)}</p>
    {#if can.cancel || can.now}
      <p class="text-meta">{waitingText(ending)}</p>
    {/if}
    <p class="text-meta waiting"><LoaderCircle size={14} class="spin" aria-hidden="true" /> {t("host.waiting")}</p>
    {#snippet footer()}
      {#if ending && answerable(ending).cancel}
        <button class="btn btn--ghost" onclick={takeBack} disabled={answering}>{t("common.cancel")}</button>
      {/if}
      {#if ending && answerable(ending).now}
        <button class="btn btn--danger" onclick={now} disabled={answering}>{t("banner.now")}</button>
      {/if}
    {/snippet}
  </Modal>
{/if}

<style>
  p {
    margin: 0;
  }
  .waiting {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
  }
  .waiting :global(.spin) {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .waiting :global(.spin) {
      animation: none;
    }
  }
</style>
