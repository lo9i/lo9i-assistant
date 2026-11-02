<script lang="ts">
  import { page } from "$app/state";
  import Bot from "@lucide/svelte/icons/bot";
  import { conversationTitle, doing, taskTitle, working } from "$lib/chat/subagents";
  import { clock } from "$lib/clock.svelte";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { duration } from "$lib/duration";
  import { localTime } from "$lib/health";
  import { t } from "$lib/i18n.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import SearchField from "$lib/ui/SearchField.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import { openConversation } from "$lib/ui/openConversation";
  import ActiveOnly from "$lib/ui/chat/subagents/ActiveOnly.svelte";
  import StatusMark from "$lib/ui/chat/subagents/StatusMark.svelte";
  import SubagentView from "$lib/ui/chat/subagents/SubagentView.svelte";

  // Every conversation's background subagents (core/background_subagents/), newest first: what each is doing, the
  // conversation it works for, when it started and ended. The one picked shows on the right as the conversation's side
  // panel shows it, to answer what it waits for, stop it or remove it. At first only those still at it are listed; the
  // Active filter off lists those that ended too.
  const { chats, notices } = useDaemon();
  const subagents = resource((c) => c.subagents.list(), ["subagents"]);
  // For the title of the conversation each works for.
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const time = clock();
  // A link can open one with ?id=<its id>.
  const linked = page.url.searchParams.get("id");
  let picked = $state<string | null>(linked);
  // A link to one opens it whether it ended or not.
  let activeOnly = $state(linked === null);
  let query = $state("");
  const active = $derived(activeOnly ? (subagents.data ?? []).filter(working) : (subagents.data ?? []));
  // By task or conversation.
  const shown = $derived(active.filter((s) => `${s.task} ${title(s.thread_id)}`.toLowerCase().includes(query.trim().toLowerCase())));
  const subagent = $derived(shown.find((s) => s.id === picked) ?? shown[0]);

  function title(threadId: string): string {
    return threadId === chats.inboxId ? t("subagentsPage.inbox") : conversationTitle(threadId, conversations.data ?? []);
  }
</script>

<TopBar title={t("subagents.title")} />

<div class="screen" class:idle={!subagent}>
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">{t("subagentsPage.title")}</h2>
        <p class="text-meta">{t("subagentsPage.hint")}</p>
      </div>
      <div class="filters">
        <ActiveOnly bind:checked={activeOnly} />
        <SearchField bind:value={query} label={t("subagentsPage.search")} />
      </div>
    </header>
    <div class="scroll">
      {#if subagents.error}
        <p class="error-text pad">{subagents.error}</p>
      {:else if subagents.data?.length === 0}
        <EmptyState icon={Bot} title={t("subagentsPage.none")} text={t("subagentsPage.noneHint")} />
      {:else if subagents.data && active.length === 0}
        <EmptyState icon={Bot} title={t("subagentsPage.noneActive")} text={t("subagentsPage.noneActiveHint")} />
      {:else if subagents.data}
        <table class="data-table">
          <thead
            ><tr
              ><th>{t("subagentsPage.status")}</th><th>{t("subagentsPage.task")}</th><th>{t("subagentsPage.conversation")}</th><th
                class="hide-narrow">{t("subagentsPage.started")}</th
              ><th class="hide-narrow">{t("subagentsPage.ended")}</th></tr
            ></thead
          >
          <tbody>
            {#each shown as s (s.id)}
              <tr class:selected={s.id === subagent?.id} onclick={() => (picked = s.id)}>
                <td>
                  <span class="state status--{s.status}"><StatusMark status={s.status} />{t(`subagents.status.${s.status}`)}</span>
                </td>
                <td class="task">
                  <button class="row-button" title={s.task} onclick={() => (picked = s.id)}>{taskTitle(s.task)}</button>
                  {#if doing(s)}<span class="doing text-caption" title={doing(s)}>{doing(s)}</span>{/if}
                </td>
                <td class="conversation">
                  {#if s.thread_id === chats.inboxId}
                    <span class="text-label">{title(s.thread_id)}</span>
                  {:else}
                    <button
                      class="link"
                      title={t("app.openItsConversation")}
                      onclick={(e) => {
                        e.stopPropagation();
                        void openConversation(chats, notices, s.thread_id);
                      }}>{title(s.thread_id)}</button
                    >
                  {/if}
                </td>
                <td class="text-label hide-narrow">{localTime(s.started_at)}</td>
                <td class="text-label hide-narrow">{s.ended_at ? localTime(s.ended_at) : ""}</td>
              </tr>
            {:else}
              <tr><td colspan="5" class="text-meta">{t("common.noMatches")}</td></tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </section>

  <div class="column">
    {#if subagent}
      <section class="details surface--glass">
        <dl>
          <dt class="micro-label">{t("subagentsPage.conversation")}</dt>
          <dd>
            {#if subagent.thread_id === chats.inboxId}
              {title(subagent.thread_id)}
            {:else}
              <button class="link" onclick={() => openConversation(chats, notices, subagent.thread_id)}>{title(subagent.thread_id)}</button>
            {/if}
          </dd>
          <dt class="micro-label">{t("subagentsPage.started")}</dt>
          <dd>{localTime(subagent.started_at)}</dd>
          {#if subagent.ended_at}
            <dt class="micro-label">{t("subagentsPage.ended")}</dt>
            <dd>{localTime(subagent.ended_at)}</dd>
          {/if}
          <dt class="micro-label">{t("subagentsPage.took")}</dt>
          <dd>{duration(subagent.started_at, subagent.ended_at || time.now)}</dd>
        </dl>
        {#key subagent.id}
          <SubagentView id={subagent.id} />
        {/key}
      </section>
    {:else}
      <section class="placeholder surface--glass">
        <EmptyState icon={Bot} title={t("subagentsPage.noneSelected")} text={t("subagentsPage.noneSelectedHint")} />
      </section>
    {/if}
  </div>
</div>

<style>
  .screen {
    display: flex;
    /* Cards take the height of their content, up to the screen; long lists scroll inside. */
    align-items: flex-start;
    gap: 16px;
    padding: 0 16px 8px;
    height: calc(100dvh - var(--top-bar-height));
    max-width: 1600px;
    margin: 0 auto;
  }
  /* With none to show, the row is as tall as the table and the placeholder matches it. */
  .idle {
    height: auto;
    align-items: stretch;
  }
  .placeholder {
    flex: 1;
  }
  /* The table takes three quarters of the width, the subagent the rest. */
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
    align-self: stretch;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
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
  .filters {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .toolbar p {
    margin: 4px 0 0;
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
  .state {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
  }
  .status--waiting {
    color: var(--color-warn);
  }
  .task {
    max-width: 0;
    width: 45%;
  }
  .task > * {
    display: block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .doing {
    font-family: var(--font-mono);
  }
  .row-button {
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    text-align: left;
    cursor: pointer;
  }
  .link {
    border: 0;
    background: none;
    padding: 0;
    color: var(--color-accent);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .link:hover {
    text-decoration: underline;
  }
  .details {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
    padding: 20px;
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
    overflow-wrap: anywhere;
  }
  dd .link {
    text-align: right;
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
    }
    .details {
      min-height: 360px;
    }
  }
</style>
