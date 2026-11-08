<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import Folder from "@lucide/svelte/icons/folder";
  import Square from "@lucide/svelte/icons/square";
  import X from "@lucide/svelte/icons/x";
  import { untrack } from "svelte";
  import type { TaskSession, TaskSessionDetails, TaskStepTaken } from "$lib/api/types";
  import { shownItems, withStep, working } from "$lib/chat/codingTasks";
  import { clock } from "$lib/clock.svelte";
  import { useDaemon } from "$lib/daemon.svelte";
  import { duration } from "$lib/duration";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import StatusMark from "../subagents/StatusMark.svelte";
  import Thread from "../Thread.svelte";

  // One coding session beside its conversation: the agent's work as the conversation's messages show (what it was
  // asked, what it says and thinks, its tool calls, the messages the user sent it, how each task ended), kept current
  // from the steps each `agent_task_step` event brings, and a box to write to the agent: between its steps while it
  // works, else as its next task in the same session. While it works it can be stopped, asked inline first; once it
  // ended, its tab closed.
  type Props = { threadId: string; session: TaskSession };
  let { threadId, session }: Props = $props();
  const { client, hub, notices } = useDaemon();
  const time = clock();
  let details = $state<TaskSessionDetails | null>(null);
  let error = $state("");
  let text = $state("");
  let sending = $state(false);
  let stopping = $state(false);
  const busy = $derived(working(session));
  const items = $derived(details ? shownItems(details, session.name) : []);
  // Its dots while it works, but not under a call already showing its own.
  const last = $derived(items.at(-1));
  const thinking = $derived(busy && !(last?.kind === "tool" && last.state === "running"));
  const ended = $derived(busy ? "" : (details?.turns.at(-1)?.finished_at ?? ""));
  const folder = $derived(session.repository.split("/").filter(Boolean).at(-1) ?? session.repository);

  async function load(): Promise<void> {
    const shown = session.id;
    try {
      const found = await client.tasks.session(threadId, shown);
      if (shown === session.id) [details, error] = [found, ""];
    } catch (e) {
      if (shown === session.id) error = describe(e);
    }
  }

  // Again when its status changes: how its task ended comes with it.
  $effect(() => {
    void session.status;
    untrack(() => void load());
  });

  $effect(() => {
    const stopSteps = hub.on(["agent_task_step"], (data) => {
      const taken = data as TaskStepTaken;
      if (taken.thread_id !== threadId || taken.session_id !== session.id || !details) return;
      const next = withStep(details, taken.task_id, taken.index, taken.step);
      if (next) details = next;
      else void load();
    });
    const stopChanges = hub.on(["tasks_beside"], () => void load());
    const stopReconnect = hub.onReconnect(() => void load());
    return () => {
      stopSteps();
      stopChanges();
      stopReconnect();
    };
  });

  async function send(): Promise<void> {
    const message = text.trim();
    if (!message || sending) return;
    sending = true;
    try {
      const sent = await client.tasks.message(threadId, session.id, message);
      text = "";
      if (sent === "later") notices.notify(t("tasks.later", { agent: session.name }), "info");
      void load();
    } catch (e) {
      notices.report(e);
    } finally {
      sending = false;
    }
  }

  function keydown(e: KeyboardEvent): void {
    if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    void send();
  }

  async function act(action: () => Promise<unknown>): Promise<void> {
    stopping = false;
    try {
      await action();
    } catch (e) {
      notices.report(e);
    }
  }
</script>

<section class="session" aria-label={session.title}>
  <div class="meta">
    <StatusMark status={session.status} />
    <span class="status status--{session.status}">{t(`tasks.status.${session.status}`)}</span>
    <span class="where" title={t("tasks.in", { folder: session.repository })}><Folder size={12} />{folder}</span>
    <span class="text-caption">{duration(session.started_at, ended || time.now)}</span>
    <span class="end">
      {#if busy}
        {#if stopping}
          <span class="ask">{t("tasks.stopTitle", { agent: session.name })}</span>
          <button class="btn btn--danger btn--sm" onclick={() => act(() => client.tasks.stop(threadId, session.id))}
            >{t("tasks.stop")}</button
          >
          <button class="btn btn--ghost btn--sm" onclick={() => (stopping = false)}>{t("common.cancel")}</button>
        {:else}
          <button class="btn btn--ghost btn--sm" title={t("tasks.stopText")} onclick={() => (stopping = true)}
            ><Square size={11} fill="currentColor" />{t("tasks.stop")}</button
          >
        {/if}
      {:else}
        <button
          class="btn btn--ghost btn--icon"
          title={t("tasks.closeHint")}
          aria-label={t("tasks.close")}
          onclick={() => act(() => client.tasks.remove(threadId, session.id))}><X size={14} /></button
        >
      {/if}
    </span>
  </div>
  {#if error}
    <p class="note error-text">{error}</p>
  {:else if !details}
    <p class="note text-caption">{t("common.loading")}</p>
  {:else}
    <div class="work">
      <Thread {items} {thinking} name={session.name} onsuggest={() => {}} />
    </div>
  {/if}
  <div class="box">
    <div class="composer">
      <textarea
        bind:value={text}
        rows={1}
        placeholder={t("tasks.placeholder", { agent: session.name })}
        aria-label={t("tasks.placeholder", { agent: session.name })}
        onkeydown={keydown}></textarea>
      <button
        class="send"
        aria-label={t("tasks.send", { agent: session.name })}
        title={t("tasks.send", { agent: session.name })}
        disabled={!text.trim() || sending}
        onclick={send}><ArrowUp size={14} /></button
      >
    </div>
    <p class="hint text-caption">
      {busy ? t("tasks.hintWorking", { agent: session.name }) : t("tasks.hintIdle", { agent: session.name })}
    </p>
  </div>
</section>

<style>
  .session {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    min-height: 0;
  }
  .meta {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 30px;
    padding: 0 6px 6px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
    font-size: var(--font-size-sm);
  }
  .status {
    font-weight: 600;
  }
  .status--running {
    color: var(--glow);
  }
  .status--failed {
    color: var(--color-danger);
  }
  .where {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--color-text-muted);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
  }
  .end {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
  }
  .ask {
    color: var(--color-text-muted);
    white-space: nowrap;
  }
  .end .btn--sm {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .work {
    display: flex;
    flex: 1;
    min-height: 0;
  }
  .note {
    flex: 1;
    margin: 0;
    padding: 8px;
  }
  .box {
    padding: 6px 4px 0;
  }
  .composer {
    display: flex;
    align-items: flex-end;
    gap: 6px;
    padding: 3px 4px 3px 10px;
    border: 1px solid var(--color-border);
    border-radius: 16px;
    background: var(--color-bg-hover-ghost);
    transition: border-color 0.12s ease;
  }
  .composer:focus-within {
    border-color: color-mix(in srgb, var(--glow) 70%, transparent);
  }
  textarea {
    flex: 1;
    border: 0;
    outline: none;
    resize: none;
    background: transparent;
    color: inherit;
    font: inherit;
    font-size: 0.92rem;
    line-height: 1.4;
    padding: 5px 0;
    max-height: 140px;
    field-sizing: content;
  }
  .send {
    display: grid;
    place-items: center;
    flex: none;
    width: 30px;
    height: 30px;
    border: 0;
    border-radius: 50%;
    background: var(--color-action-primary);
    color: var(--color-action-on-primary);
    cursor: pointer;
    transition: transform 0.12s ease;
  }
  .send:hover:not(:disabled) {
    transform: scale(1.05);
  }
  .send:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .hint {
    margin: 4px 10px 0;
  }
</style>
