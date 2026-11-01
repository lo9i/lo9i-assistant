<script lang="ts">
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import Wrench from "@lucide/svelte/icons/wrench";
  import { untrack } from "svelte";
  import type { Decision, SubagentChanged, SubagentDetails, SubagentStepTaken } from "$lib/api/types";
  import { asked, withStep, working } from "$lib/chat/subagents";
  import { inlineArg } from "$lib/chat/transcript";
  import { clock } from "$lib/clock.svelte";
  import { useDaemon } from "$lib/daemon.svelte";
  import { duration } from "$lib/duration";
  import { t } from "$lib/i18n.svelte";
  import { markdown } from "$lib/markdown";
  import { describe } from "$lib/notices";
  import Confirm from "$lib/ui/Confirm.svelte";
  import ApprovalModal from "../ApprovalModal.svelte";
  import StatusMark from "./StatusMark.svelte";

  // One background subagent in place of the cards: its task, what it waits for the user's answer to, its steps as they
  // come (each step's tool and what it was called with, and once it finished, what it answered), and how it ended.
  // While it works it can be stopped, which asks first; once it ended, removed. Back to the cards only in the panel: the
  // Subagents page lists them beside it.
  type Props = { id: string; onback?: () => void };
  let { id, onback }: Props = $props();
  const { client, hub, notices } = useDaemon();
  const time = clock();
  let details = $state<SubagentDetails | null>(null);
  let error = $state("");
  let answering = $state(false);
  let stopping = $state(false);
  const subagent = $derived(details?.subagent ?? null);
  const question = $derived(subagent ? (asked(subagent)[0] ?? null) : null);

  async function load(): Promise<void> {
    const shown = id;
    try {
      const found = await client.subagents.get(shown);
      if (shown === id) [details, error] = [found, ""];
    } catch (e) {
      if (shown === id) error = describe(e);
    }
  }

  $effect(() => {
    void id;
    untrack(() => {
      details = null;
      void load();
    });
  });

  $effect(() => {
    const shown = id;
    const stopChanges = hub.on(["subagents"], (data) => {
      if ((data as SubagentChanged).id === shown) void load();
    });
    const stopSteps = hub.on(["subagent_step"], (data) => {
      const taken = data as SubagentStepTaken;
      if (taken.id === shown && details) details = { ...details, steps: withStep(details.steps, taken.step) };
    });
    const stopReconnect = hub.onReconnect(() => void load());
    return () => {
      stopChanges();
      stopSteps();
      stopReconnect();
    };
  });

  async function answer(decision: Decision): Promise<void> {
    const interruptId = question?.interrupt_id;
    answering = false;
    if (!interruptId) return;
    try {
      if (!(await client.subagents.answer(id, interruptId, decision))) notices.notify(t("subagents.notWaiting"), "warning");
    } catch (e) {
      notices.report(e);
    }
  }

  async function act(action: (id: string) => Promise<unknown>): Promise<void> {
    try {
      await action(id);
    } catch (e) {
      notices.report(e);
    }
    void load();
  }
</script>

<section class="subagent" aria-label={t("subagents.one")}>
  <header>
    {#if onback}
      <button class="btn btn--ghost btn--icon" title={t("subagents.back")} aria-label={t("subagents.back")} onclick={onback}
        ><ArrowLeft size={14} /></button
      >
    {/if}
    {#if subagent}
      <StatusMark status={subagent.status} />
      <span class="status">{t(`subagents.status.${subagent.status}`)}</span>
      <span class="text-caption">{duration(subagent.started_at, subagent.ended_at || time.now)}</span>
    {/if}
  </header>
  {#if error}
    <p class="note error-text">{error}</p>
  {:else if !subagent || !details}
    <p class="note text-caption">{t("common.loading")}</p>
  {:else}
    <div class="body">
      <p class="task">{subagent.task}</p>
      {#if subagent.agent}<p class="text-caption">{t("subagents.named", { agent: subagent.agent })}</p>{/if}
      <div class="actions">
        {#if question}
          <button class="btn btn--primary btn--sm" onclick={() => (answering = true)}>{t("subagents.answer")}</button>
        {/if}
        {#if working(subagent)}
          <button class="btn btn--danger btn--sm" onclick={() => (stopping = true)}>{t("subagents.stop")}</button>
        {:else}
          <button class="btn btn--ghost btn--sm" onclick={() => act((id) => client.subagents.remove(id))}>{t("subagents.remove")}</button>
        {/if}
      </div>
      {#if question}
        <p class="waiting">
          {t("subagents.asks", { what: String(question.request.command ?? question.request.message ?? question.request.reason ?? "") })}
        </p>
      {/if}
      {#if subagent.status === "done"}
        <h3 class="micro-label">{t("subagents.answerTitle")}</h3>
        <div class="prose result">{@html markdown(subagent.result)}</div>
      {:else if subagent.status === "failed"}
        <h3 class="micro-label">{t("subagents.failedTitle")}</h3>
        <p class="error-text">{subagent.result}</p>
      {/if}
      <h3 class="micro-label">{t("subagents.steps", { count: details.steps.length })}</h3>
      {#if subagent.status === "running" && !subagent.step}<p class="text-caption">{t("subagents.thinking")}</p>{/if}
      <div class="steps">
        {#each details.steps as step (step.index)}
          {@const arg = inlineArg(step.args)}
          <details class="step" class:running={!step.done}>
            <summary>
              <Wrench size={12} />
              <span class="name">{step.name}</span>
              {#if arg}<span class="arg" title={arg}>{arg}</span>{/if}
              {#if !step.done}<span class="dots"><i></i><i></i><i></i></span>{/if}
              <span class="chevron"><ChevronRight size={12} /></span>
            </summary>
            {#if arg}<pre>{arg}</pre>{:else if Object.keys(step.args).length}<pre>{JSON.stringify(step.args, null, 2)}</pre>{/if}
            {#if step.output}<pre>{step.output}</pre>{/if}
          </details>
        {/each}
      </div>
    </div>
  {/if}
</section>

{#if answering && question}
  <ApprovalModal approval={question} onanswer={(d) => void answer(d)} />
{/if}
{#if stopping}
  <Confirm
    title={t("subagents.stopTitle")}
    text={t("subagents.stopText")}
    action={t("subagents.stop")}
    onanswer={(yes) => {
      stopping = false;
      if (yes) void act((id) => client.subagents.stop(id));
    }}
  />
{/if}

<style>
  .subagent {
    display: flex;
    flex-direction: column;
    min-height: 0;
    flex: 1;
  }
  header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 4px 6px;
  }
  .status {
    flex: 1;
    font-weight: 600;
  }
  .body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 6px 4px 0;
    border-top: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .task {
    margin: 0 0 8px;
    white-space: pre-wrap;
    font-size: var(--font-size-sm);
  }
  .actions {
    display: flex;
    gap: 6px;
    margin-bottom: 8px;
  }
  .waiting {
    margin: 0 0 8px;
    padding: 6px 8px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-warn) 12%, transparent);
    font-size: var(--font-size-sm);
    overflow-wrap: anywhere;
  }
  h3 {
    margin: 12px 0 6px;
  }
  .result {
    font-size: var(--font-size-sm);
  }
  .steps {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .step summary {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 6px;
    border-radius: var(--radius-sm);
    list-style: none;
    cursor: pointer;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
  }
  .step summary::-webkit-details-marker {
    display: none;
  }
  .step summary:hover {
    background: var(--color-bg-hover-ghost);
  }
  .name {
    font-weight: 600;
    color: var(--color-text-primary);
  }
  .arg {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
  }
  .chevron {
    display: flex;
    margin-left: auto;
    transition: transform 0.15s ease;
  }
  .step[open] .chevron {
    transform: rotate(90deg);
  }
  pre {
    margin: 4px 0 6px;
    padding: 8px 10px;
    max-height: 240px;
    overflow: auto;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-text-primary) 4%, transparent);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .dots {
    display: inline-flex;
    gap: 2px;
  }
  .dots i {
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background: currentColor;
    animation: blink 1.2s infinite ease-in-out;
  }
  .dots i:nth-child(2) {
    animation-delay: 0.2s;
  }
  .dots i:nth-child(3) {
    animation-delay: 0.4s;
  }
  @keyframes blink {
    0%,
    80%,
    100% {
      opacity: 0.25;
    }
    40% {
      opacity: 1;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .dots i {
      animation: none;
    }
  }
  .note {
    margin: 0;
    padding: 4px 8px;
  }
</style>
