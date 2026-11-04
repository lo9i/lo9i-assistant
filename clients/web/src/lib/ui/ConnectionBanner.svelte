<script lang="ts">
  import { updated } from "$app/state";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import Power from "@lucide/svelte/icons/power";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import WifiOff from "@lucide/svelte/icons/wifi-off";
  import X from "@lucide/svelte/icons/x";
  import { DaemonUnavailableError } from "$lib/api/errors";
  import { external, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { answerable, coming as comingOf, comingText, noticeShown, pendingDetail, pendingTitle, type Coming } from "$lib/shutdown";

  // Says, on every page, what the daemon is up to when the page can't simply go on: a restart or stop coming (an
  // `ending` event, whoever asked for it), the daemon away while its event stream is lost (a restart, a computer
  // that slept), and a new version of this page (an update installed, the web app built again: the build this tab
  // runs is no longer the one the daemon serves). The pages load again by themselves when the stream opens again.
  let { name }: { name: string } = $props();
  const { client, hub, notices } = useDaemon();
  const connection = external(hub.subscribeConnection, hub.getConnection);
  let coming = $state<Coming | null>(null);
  let newVersion = $state(false);
  // The notice the user put away, so it no longer covers the message box: until what it says changes (another kind
  // of ending, the daemon back, a newer build). Asking for the same restart again doesn't bring it back: a tag at the
  // top of the page says it's still coming, and opens it again.
  let dismissed = $state("");
  const shown = $derived(noticeShown(connection.current === "lost", coming, newVersion));
  $effect(() => {
    if (!shown) dismissed = "";
  });

  // The event says what's coming at once; who asked, when, and the queued messages come from the daemon after it.
  $effect(() => {
    void pending();
    return hub.on(["ending"], (data) => {
      coming = comingOf(data);
      if (coming) void pending();
    });
  });
  // How many runs and queued messages it still waits for; once none, it's going ahead and what's coming stays.
  $effect(() => hub.on(["run_finished", "queued_messages"], () => void (coming && pending())));

  /** A restart or stop asked for before this page loaded, or the runs it waits for now. */
  async function pending(): Promise<void> {
    try {
      const found = comingOf(await client.system.ending());
      if (found) coming = found;
    } catch (e) {
      // Unreachable: the banner says so already, and this is read again when the stream opens.
      if (!(e instanceof DaemonUnavailableError)) notices.report(e);
    }
  }
  // While it waits: Cancel keeps the daemon running (not for an installed update), Now cancels the runs so it goes
  // ahead.
  let answering = $state(false);
  async function answer(act: () => Promise<unknown>, after: () => void): Promise<void> {
    answering = true;
    try {
      await act();
      after();
    } catch (e) {
      notices.report(e);
      void pending();
    } finally {
      answering = false;
    }
  }
  const takeBack = () =>
    answer(
      () => client.system.takeBackEnding(),
      () => (coming = null),
    );
  const now = () =>
    answer(
      () => client.system.endNow(),
      () => {},
    );

  // Asks for the build's version.json, which a new build replaces: no polling, once per reconnection (an update
  // restarts the daemon) and when the daemon says the web app was built again (`web_build`).
  function checkVersion(): void {
    void updated.check().then((changed) => (newVersion = changed));
  }
  $effect(() => hub.on(["web_build"], checkVersion));
  $effect(() =>
    hub.onReconnect(() => {
      coming = null;
      void pending();
      checkVersion();
    }),
  );
</script>

{#snippet dismiss()}
  <button class="dismiss" aria-label={t("common.dismiss")} title={t("common.dismiss")} onclick={() => (dismissed = shown)}>
    <X size={14} />
  </button>
{/snippet}

{#if shown && shown === dismissed}
  <button class="tag" class:fresh={!coming && connection.current !== "lost"} title={t("banner.tag.show")} onclick={() => (dismissed = "")}>
    {#if connection.current === "lost"}
      <span class="spin"><LoaderCircle size={12} /></span>{t("banner.reconnecting")}
    {:else if coming}
      <RefreshCw size={12} />{t(coming.ending === "stop" ? "banner.tag.stop" : "banner.tag.restart")}
      {#if coming.waiting}<span class="waiting">{coming.waiting}</span>{/if}
    {:else}
      <RefreshCw size={12} />{t("banner.tag.fresh")}
    {/if}
  </button>
{:else if connection.current === "lost"}
  <div class="banner surface--glass" role="status" aria-live="polite">
    {#if coming?.ending === "stop"}
      <Power size={16} />
      <span><strong>{t("banner.stopped", { name })}</strong> {t("banner.stoppedHint")}</span>
    {:else if coming}
      <RefreshCw size={16} />
      <span><strong>{t("banner.restarting", { name })}</strong> {t("banner.reconnecting")}</span>
    {:else}
      <WifiOff size={16} />
      <span><strong>{t("banner.unreachable", { name })}</strong> {t("banner.unreachableHint")}</span>
    {/if}
    <span class="spin"><LoaderCircle size={16} /></span>
    {@render dismiss()}
  </div>
{:else if coming}
  <div class="banner surface--glass" role="status" aria-live="polite">
    <RefreshCw size={16} />
    <span>
      <strong>{pendingTitle(coming)}</strong>
      {comingText(name, coming)}
      {#if pendingDetail(coming)}<span class="detail">{pendingDetail(coming)}</span>{/if}
    </span>
    {#if answerable(coming).cancel}
      <button class="btn btn--sm btn--ghost" onclick={takeBack} disabled={answering}>{t("common.cancel")}</button>
    {/if}
    {#if answerable(coming).now}
      <button class="btn btn--sm btn--danger" onclick={now} disabled={answering}>{t("banner.now")}</button>
    {/if}
    {@render dismiss()}
  </div>
{:else if newVersion}
  <div class="banner surface--glass fresh" role="status" aria-live="polite">
    <RefreshCw size={16} />
    <span><strong>{t("banner.newVersion", { name })}</strong> {t("banner.reloadToUse")}</span>
    <button class="btn btn--sm btn--primary" onclick={() => location.reload()}>{t("banner.reload")}</button>
    {@render dismiss()}
  </div>
{/if}

<style>
  .banner {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    z-index: var(--z-popover);
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: calc(100vw - 32px);
    padding: 10px 10px 10px 16px;
    border-color: color-mix(in srgb, var(--color-warn) 45%, var(--surface-glass-border));
    color: var(--color-warn);
    font-size: var(--font-size-sm);
    animation: drop 0.18s ease;
  }
  .fresh {
    border-color: color-mix(in srgb, var(--color-accent) 45%, var(--surface-glass-border));
    color: var(--color-accent);
  }
  /* What a notice put away leaves: a small tag at the top of the page, out of the way of the message box. */
  .tag {
    position: fixed;
    top: 14px;
    left: 50%;
    transform: translateX(-50%);
    z-index: var(--z-popover);
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border: 1px solid color-mix(in srgb, var(--color-warn) 55%, transparent);
    border-radius: var(--radius-full);
    background: color-mix(in srgb, var(--color-warn) 14%, var(--surface-raised-bg));
    color: var(--color-warn);
    font: inherit;
    font-size: var(--font-size-xs);
    font-weight: 600;
    cursor: pointer;
  }
  .tag.fresh {
    border-color: color-mix(in srgb, var(--color-accent) 55%, transparent);
    background: color-mix(in srgb, var(--color-accent) 12%, var(--surface-raised-bg));
    color: var(--color-accent);
  }
  .tag .waiting {
    min-width: 16px;
    padding: 0 4px;
    border-radius: 8px;
    background: color-mix(in srgb, var(--color-warn) 25%, transparent);
    font-variant-numeric: tabular-nums;
    text-align: center;
  }
  .dismiss {
    display: grid;
    place-items: center;
    flex: none;
    width: 26px;
    height: 26px;
    border: 0;
    border-radius: 50%;
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .dismiss:hover {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  strong {
    font-weight: 600;
  }
  .detail {
    color: var(--color-text-muted);
  }
  span {
    color: var(--color-text-primary);
  }
  .spin {
    display: inline-flex;
    color: var(--color-warn);
    animation: spin 0.9s linear infinite;
  }
  @keyframes drop {
    from {
      transform: translate(-50%, 8px);
      opacity: 0;
    }
  }
</style>
