<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import CircleCheck from "@lucide/svelte/icons/circle-check";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import Stethoscope from "@lucide/svelte/icons/stethoscope";
  import type { Cause } from "$lib/api/types";
  import { compact } from "$lib/conversationStats";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { changeLabel, contextShare, partSize, times } from "$lib/doctor";
  import { runQuery } from "$lib/jobs";
  import { localTime } from "$lib/health";
  import { formatDate, t } from "$lib/i18n.svelte";
  import { levelLabel } from "$lib/logs";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import { openConversation } from "$lib/ui/openConversation";
  import TopBar from "$lib/ui/TopBar.svelte";
  import SettingsTabs from "$lib/ui/settings/SettingsTabs.svelte";

  // The daemon's health check (core/doctor/): the day's problems in its log and its conversations, grouped by cause,
  // and the context a new conversation starts with, each against the day before. The daemon checks each day once it
  // ended; Check now checks today so far. A cause that's only noise is marked as known and left out from then on.
  const { client, chats, notices } = useDaemon();
  const doctor = resource((c) => c.doctor.get(), ["doctor"]);
  const report = $derived(doctor.data?.report ?? null);
  // Until one is picked: the one an alert opened, or the first.
  let picked = $state<string | null>(page.url.searchParams.get("c"));
  const cause = $derived(report?.causes.find((c) => c.id === picked) ?? report?.causes[0]);

  async function act(action: () => Promise<unknown>): Promise<void> {
    try {
      await action();
    } catch (e) {
      notices.report(e);
    }
  }

  function kind(c: Cause): string {
    return c.kind === "log" ? t("doctorPage.logLevel", { level: levelLabel(c.level).toLowerCase() }) : t("tokens.conversation");
  }

  function checked(): string {
    if (!report) return "";
    const day = formatDate(`${report.day}T12:00:00`, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
    const span = report.whole_day ? t("doctorPage.wholeDay", { day }) : t("doctorPage.soFar", { day });
    const compared = report.compared_with ? t("doctorPage.comparedWith", { day: report.compared_with }) : t("doctorPage.nothingToCompare");
    return t("doctorPage.checked", { span, when: localTime(report.at), compared });
  }
</script>

<!-- A settings tab of its own page. -->
<TopBar title={t("nav.settings")} />

<div class="shell">
  <SettingsTabs active="doctor" />
  <div class="screen">
    <section class="table-card surface--glass">
      <header class="toolbar">
        <div>
          <h2 class="text-heading">{t("alerts.healthCheck")}</h2>
          <p class="text-meta">
            {report ? checked() : t("doctorPage.daily")}
            {t("doctorPage.clickCause")}
          </p>
        </div>
        <div class="actions">
          {#if report}<span class="pill">{report.causes.length}</span>{/if}
          <button
            class="btn btn--primary btn--sm"
            disabled={doctor.data?.checking}
            onclick={() => act(() => client.doctor.check())}
            title={t("doctorPage.checkTodayHint")}
          >
            <RefreshCw size={16} />
            <span class="hide-narrow">{doctor.data?.checking ? t("webSearch.checking") : t("doctorPage.checkNow")}</span>
          </button>
        </div>
      </header>
      <div class="scroll">
        {#if doctor.error}
          <p class="error-text pad">{doctor.error}</p>
        {:else if doctor.data && !report}
          <EmptyState icon={Stethoscope} title={t("doctorPage.notChecked")} text={t("doctorPage.notCheckedHint")} />
        {:else if report && report.causes.length === 0}
          <EmptyState icon={CircleCheck} title={t("doctorPage.nothingWrong")} text={t("doctorPage.nothingWrongHint")} />
        {:else if report && cause}
          <table class="data-table">
            <thead>
              <tr
                ><th>{t("doctorPage.cause")}</th><th class="hide-narrow">{t("alerts.kind")}</th><th>{t("doctorPage.howOften")}</th><th
                  class="hide-narrow">{t("doctorPage.last")}</th
                ></tr
              >
            </thead>
            <tbody>
              {#each report.causes as c (c.id)}
                <tr class:selected={c.id === cause.id} onclick={() => (picked = c.id)}>
                  <td>
                    <button class="row-button" onclick={() => (picked = c.id)}>
                      {#if c.change}<span class="pill pill--danger">{changeLabel(c)}</span>{/if}
                      {c.title}
                    </button>
                  </td>
                  <td class="text-label hide-narrow">{kind(c)}</td>
                  <td class="text-label">{times(c)}</td>
                  <td class="text-label hide-narrow">{localTime(c.last)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>
    </section>

    <div class="column">
      {#if cause}
        <section class="details surface--glass">
          <header>
            <h2 class="text-heading">{cause.title}</h2>
            {#if cause.change}<span class="pill pill--danger">{changeLabel(cause)}</span>{/if}
          </header>
          <dl>
            <dt class="micro-label">{t("alerts.kind")}</dt>
            <dd>{kind(cause)}</dd>
            {#if cause.where}<dt class="micro-label">{t("doctorPage.where")}</dt>
              <dd class="mono">{cause.where}</dd>{/if}
            <dt class="micro-label">{t("doctorPage.howOften")}</dt>
            <dd>{times(cause)}</dd>
            <dt class="micro-label">{t("doctorPage.first")}</dt>
            <dd>{localTime(cause.first)}</dd>
            <dt class="micro-label">{t("doctorPage.last")}</dt>
            <dd>{localTime(cause.last)}</dd>
          </dl>
          {#if cause.threads.length}
            <div class="threads">
              {#each cause.threads as thread (thread.thread_id)}
                {#if thread.job}
                  <!-- A scheduled job's run: its conversation isn't listed, the Jobs page shows it. -->
                  <a class="btn btn--ghost btn--sm" href={`${resolve("/jobs")}${runQuery(thread.job, thread.run_at)}`}>{thread.title}</a>
                {:else}
                  <button class="btn btn--ghost btn--sm" onclick={() => openConversation(chats, notices, thread.thread_id)}
                    >{thread.title || t("common.untitled")}</button
                  >
                {/if}
              {/each}
            </div>
          {/if}
          {#if cause.example}<pre class="example">{cause.example}</pre>{/if}
          <div class="actions">
            <button
              class="btn btn--neutral btn--sm"
              title={t("doctorPage.markKnownHint")}
              onclick={() => act(() => client.doctor.markKnown(cause.id))}>{t("doctorPage.markKnown")}</button
            >
          </div>
        </section>
      {/if}

      {#if report}
        <section class="details surface--glass">
          <header>
            <h2 class="text-heading">{t("doctorPage.startingContext")}</h2>
            <span class="pill" class:pill--danger={report.context.too_large}>{contextShare(report.context)}</span>
          </header>
          <p class="text-meta">
            {t("doctorPage.contextText", { tokens: compact(report.context.tokens), window: compact(report.context.window) })}
          </p>
          <dl>
            {#each report.context.parts as part (part.name)}
              <dt class="micro-label">{part.name}</dt>
              <dd>{partSize(part)}</dd>
            {/each}
          </dl>
        </section>
      {/if}

      {#if report?.gone.length}
        <section class="details surface--glass">
          <h2 class="text-heading">{t("doctorPage.gone", { day: report.compared_with })}</h2>
          <ul>
            {#each report.gone as g (g.id)}<li>{g.title}</li>{/each}
          </ul>
        </section>
      {/if}

      {#if doctor.data?.known.length}
        <section class="details surface--glass">
          <h2 class="text-heading">{t("doctorPage.known")}</h2>
          <p class="text-meta">{t("doctorPage.knownHint")}</p>
          <ul class="known">
            {#each doctor.data.known as k (k.id)}
              <li>
                <span>{k.title}</span>
                <button class="btn btn--ghost btn--sm" onclick={() => act(() => client.doctor.forgetKnown(k.id))}
                  >{t("doctorPage.notNoise")}</button
                >
              </li>
            {/each}
          </ul>
        </section>
      {/if}
    </div>
  </div>
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 0 16px 16px;
    max-width: 1600px;
    margin: 0 auto;
  }
  .screen {
    display: flex;
    /* Cards take the height of their content, up to the screen; long lists scroll inside. */
    align-items: flex-start;
    gap: 16px;
    /* Below the title bar, the settings tabs and the gaps around them. */
    height: calc(100dvh - var(--top-bar-height) - 72px);
  }
  /* The table takes three quarters of the width, the details the rest. */
  .table-card {
    flex: 3 1 0;
    min-width: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .column {
    flex: 1 1 0;
    min-width: 0;
    max-height: 100%;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
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
  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
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
  .details {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
  }
  .details header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .details h2,
  .details p {
    margin: 0;
    overflow-wrap: anywhere;
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
  .mono {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    overflow-wrap: anywhere;
  }
  .threads {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .example {
    margin: 0;
    padding: 12px;
    max-height: 240px;
    overflow: auto;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-danger) 8%, transparent);
    color: var(--color-text-primary);
    font-size: var(--font-size-xs);
    white-space: pre-wrap;
    word-break: break-word;
  }
  ul {
    margin: 0;
    padding-left: 18px;
  }
  .known {
    list-style: none;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .known li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    overflow-wrap: anywhere;
  }
  /* Stacked, the page scrolls: each part takes its own height instead of a share of the screen. */
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
      align-items: stretch;
      height: auto;
    }
    .table-card,
    .column {
      flex: none;
      max-height: none;
    }
  }
</style>
