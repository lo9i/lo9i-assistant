<script lang="ts">
  import { page } from "$app/state";
  import CircleCheck from "@lucide/svelte/icons/circle-check";
  import ListTodo from "@lucide/svelte/icons/list-todo";
  import RotateCcw from "@lucide/svelte/icons/rotate-ccw";
  import Sunrise from "@lucide/svelte/icons/sunrise";
  import VolumeX from "@lucide/svelte/icons/volume-x";
  import X from "@lucide/svelte/icons/x";
  import type { LoopStatus, OpenLoop, ProactiveWork } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { localTime } from "$lib/health";
  import { formatList, t, type Key } from "$lib/i18n.svelte";
  import { markdown } from "$lib/markdown";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import { openConversation } from "$lib/ui/openConversation";
  import ProactiveCard from "$lib/ui/settings/ProactiveCard.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  // The assistant's own initiative (core/proactive/): the open loops, the latest briefing and review, and their
  // settings. A briefing or reminder notification opens here, as ?loop=<id> opens that loop.
  const { client, chats, notices } = useDaemon();
  const proactive = resource((c) => c.proactive.get(), ["proactive"]);
  const FILTERS: Array<[LoopStatus, Key]> = [
    ["open", "briefingPage.open"],
    ["done", "briefingPage.done"],
    ["dismissed", "briefingPage.dismissed"],
  ];
  let filter = $state<LoopStatus>("open");
  let picked = $state<string | null>(page.url.searchParams.get("loop"));
  const listed = $derived((proactive.data?.loops ?? []).filter((l) => (l.status ?? "open") === filter));
  const loop = $derived(listed.find((l) => l.id === picked) ?? listed[0]);
  const briefing = $derived(proactive.data?.briefing);
  const review = $derived(proactive.data?.reviews?.[0]);
  const running = $derived(proactive.data?.running ?? []);

  function source(l: OpenLoop): string {
    return t(`briefingPage.sources.${l.source}` as Key);
  }

  function act(action: () => Promise<unknown>): void {
    action().catch(notices.report);
  }

  function close(l: OpenLoop, status: LoopStatus, stopSuggesting = false): void {
    act(() => client.proactive.closeLoop(l.id, status, stopSuggesting));
  }

  function run(work: ProactiveWork): void {
    act(() => client.proactive.run(work));
  }
</script>

<TopBar title={t("briefingPage.title")}>
  {#snippet actions()}
    <button class="btn btn--primary" disabled={running.includes("briefing")} onclick={() => run("briefing")}
      ><Sunrise size={16} /><span class="hide-narrow"
        >{running.includes("briefing") ? t("briefingPage.briefing") : t("briefingPage.briefNow")}</span
      ></button
    >
  {/snippet}
</TopBar>

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">{t("briefingPage.loops")}</h2>
        <p class="text-meta">{t("briefingPage.loopsHint")}</p>
      </div>
      <div class="controls">
        <div class="tabs" role="radiogroup" aria-label={t("briefingPage.loops")}>
          {#each FILTERS as [value, label] (value)}
            <button role="radio" aria-checked={filter === value} class:active={filter === value} onclick={() => (filter = value)}
              >{t(label)}</button
            >
          {/each}
        </div>
        {#if proactive.data}<span class="pill">{listed.length}</span>{/if}
      </div>
    </header>
    <div class="scroll">
      {#if proactive.error}
        <p class="error-text pad">{proactive.error}</p>
      {:else if proactive.data && !listed.length}
        {#if filter === "open"}
          <EmptyState icon={ListTodo} title={t("briefingPage.none")} text={t("briefingPage.noneHint")} />
        {:else}
          <EmptyState icon={ListTodo} title={t("briefingPage.noneClosed")} text={t("briefingPage.noneClosedHint")} />
        {/if}
      {:else if loop}
        <table class="data-table">
          <thead
            ><tr
              ><th>{t("briefingPage.what")}</th><th class="hide-narrow">{t("briefingPage.kind")}</th><th>{t("briefingPage.due")}</th><th
                class="hide-narrow">{t("briefingPage.from")}</th
              >{#if filter === "open"}<th class="quick" aria-label={t("briefingPage.markDone")}></th>{/if}</tr
            ></thead
          >
          <tbody>
            {#each listed as l (l.id)}
              <tr class:selected={l.id === loop.id} onclick={() => (picked = l.id)}>
                <td><button class="row-button" onclick={() => (picked = l.id)}>{l.text}</button></td>
                <td class="hide-narrow text-label">{l.kind}</td>
                <td class="text-label">{l.due}</td>
                <td class="hide-narrow text-label">{source(l)}</td>
                {#if filter === "open"}
                  <td class="quick">
                    <button
                      class="btn btn--icon"
                      aria-label={t("briefingPage.markDoneThis")}
                      title={t("briefingPage.markDoneThis")}
                      onclick={(e) => (e.stopPropagation(), close(l, "done"))}><CircleCheck size={16} /></button
                    >
                  </td>
                {/if}
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </section>

  <div class="column">
    {#if loop}
      <section class="details surface--glass">
        <h2 class="text-heading">{loop.text}</h2>
        <dl>
          {#if loop.kind}<dt class="micro-label">{t("briefingPage.kind")}</dt>
            <dd>{loop.kind}</dd>{/if}
          {#if loop.due}<dt class="micro-label">{t("briefingPage.due")}</dt>
            <dd>{loop.due}</dd>{/if}
          {#if loop.remind_at}<dt class="micro-label">{t("briefingPage.remindAt")}</dt>
            <dd>{localTime(loop.remind_at)}</dd>{/if}
          <dt class="micro-label">{t("briefingPage.from")}</dt>
          <dd>{source(loop)}</dd>
          <dt class="micro-label">{t("briefingPage.since")}</dt>
          <dd>{localTime(loop.created_at)}</dd>
        </dl>
        <div class="actions">
          {#if (loop.status ?? "open") === "open"}
            <button class="btn btn--neutral btn--sm" onclick={() => close(loop, "done")}
              ><CircleCheck size={14} />{t("briefingPage.markDone")}</button
            >
            <button class="btn btn--ghost btn--sm" onclick={() => close(loop, "dismissed")}
              ><X size={14} />{t("briefingPage.dismiss")}</button
            >
            {#if loop.kind}
              <button class="btn btn--ghost btn--sm" onclick={() => close(loop, "dismissed", true)}
                ><VolumeX size={14} />{t("briefingPage.stopSuggesting", { kind: loop.kind })}</button
              >
            {/if}
          {:else}
            <button class="btn btn--neutral btn--sm" onclick={() => close(loop, "open")}
              ><RotateCcw size={14} />{t("briefingPage.reopen")}</button
            >
          {/if}
          {#if loop.thread_id && loop.thread_id !== chats.inboxId}
            <button class="btn btn--ghost btn--sm" onclick={() => openConversation(chats, notices, loop.thread_id ?? "")}
              >{t("app.openItsConversation")}</button
            >
          {/if}
        </div>
      </section>
    {:else if proactive.data}
      <section class="details surface--glass">
        <EmptyState icon={ListTodo} title={t("briefingPage.noneSelected")} text={t("briefingPage.noneSelectedHint")} />
      </section>
    {/if}

    <section class="details surface--glass">
      <h2 class="text-heading">{t("briefingPage.latest")}</h2>
      {#if briefing}
        <p class="text-meta">
          {localTime(briefing.at)} ·
          {#if briefing.status === "sent"}
            {briefing.channels?.length ? t("briefingPage.sentTo", { channels: formatList(briefing.channels) }) : t("briefingPage.onlyHere")}
          {:else if briefing.status === "nothing"}
            {t("briefingPage.nothing")}
          {:else}
            <span class="error-text">{t("briefingPage.failed", { error: briefing.error ?? "" })}</span>
          {/if}
        </p>
        {#if briefing.text}<div class="prose">{@html markdown(briefing.text)}</div>{/if}
      {:else if proactive.data}
        <p class="text-meta">
          {t("briefingPage.notYet")}: {t("briefingPage.notYetHint", { time: proactive.data.settings.briefing_time ?? "08:00" })}
        </p>
      {/if}
    </section>

    <section class="details surface--glass">
      <header>
        <h2 class="text-heading">{t("briefingPage.review")}</h2>
        <button class="btn btn--ghost btn--sm" disabled={running.includes("nightly")} onclick={() => run("nightly")}
          >{t("briefingPage.reviewNow")}</button
        >
      </header>
      {#if review}
        <p class="text-meta">
          {review.kind === "weekly" ? t("briefingPage.weekly") : t("briefingPage.nightly")} · {localTime(review.at)} ·
          {t("briefingPage.reviewed", { added: review.added ?? 0, closed: review.closed ?? 0 })}
        </p>
        {#if review.error}<p class="error-text">{t("briefingPage.failed", { error: review.error })}</p>{/if}
        {#if review.summary}<p class="text">{review.summary}</p>{/if}
        {#if review.suggestions?.length}
          <h3 class="micro-label">{t("briefingPage.suggestions")}</h3>
          <ul>
            {#each review.suggestions as s (s.text)}<li>{s.text} <span class="text-caption">{s.kind}</span></li>{/each}
          </ul>
        {/if}
      {:else if proactive.data}
        <p class="text-meta">{t("briefingPage.noReview")}</p>
      {/if}
    </section>

    <ProactiveCard />
  </div>
</div>

<style>
  .screen {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 0 16px 8px;
    height: calc(100dvh - var(--top-bar-height));
    max-width: 1600px;
    margin: 0 auto;
  }
  .table-card {
    flex: 3 1 0;
    min-width: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  /* The loop, the briefing, the review and the settings: it scrolls when they're taller than the screen. */
  .column {
    flex: 1 1 0;
    align-self: stretch;
    min-width: 320px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
    overflow-y: auto;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 16px 24px;
    min-height: 66px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .scroll {
    overflow-y: auto;
    min-height: 0;
  }
  .data-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .pad {
    padding: 24px;
  }
  tr {
    cursor: pointer;
  }
  tr.selected {
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
  }
  tr.selected td:first-child {
    box-shadow: inset 3px 0 0 var(--color-accent);
  }
  .row-button {
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    text-align: left;
    cursor: pointer;
  }
  /* Marking a loop done from its row; the negative margin keeps the row as tall as the others. */
  .quick {
    width: 1%;
    text-align: right;
  }
  .quick .btn {
    --btn-icon-size: 28px;
    margin: -6px 0;
  }
  .details {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 20px;
  }
  .details header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .details p,
  h2,
  h3 {
    margin: 0;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    margin: 0;
    align-items: baseline;
  }
  dd {
    margin: 0;
    text-align: right;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  ul {
    margin: 0;
    padding-left: 18px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .prose {
    overflow-wrap: anywhere;
  }
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
      align-items: stretch;
      height: auto;
    }
    .table-card,
    .column {
      flex: none;
      min-width: 0;
      overflow: visible;
    }
  }
</style>
