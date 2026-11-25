<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import { untrack } from "svelte";
  import type { TaskSession, TaskSessionDetails, TaskStepTaken } from "$lib/api/types";
  import { shownItems, withStep, working } from "$lib/chat/codingTasks";
  import { Resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import Thread from "../Thread.svelte";
  import TaskStatus from "./TaskStatus.svelte";

  // One coding session beside its conversation: the agent's work as the conversation's messages show (what it was
  // asked, what it says and thinks, its tool calls, the messages the user sent it, how each task ended), kept current
  // from the steps each `agent_task_step` event brings, and a box to write to the agent: between its steps while it
  // works, else as its next task in the same session (its row in TasksPanel stops or closes it). Under the box, its
  // status line (TaskStatus).
  type Props = { threadId: string; session: TaskSession };
  let { threadId, session }: Props = $props();
  const { client, hub, notices } = useDaemon();
  // One load on its way at a time, once more after it when something changed meanwhile: with several agents busy, the
  // events that ask for one come faster than a session's work loads, and a load each would never catch up.
  const loaded = new Resource<TaskSessionDetails>(() => client.tasks.session(threadId, session.id));
  const details = $derived(loaded.data ?? null);
  const error = $derived(loaded.error ?? "");
  // Its status alone, not the session: the list beside it is loaded again on every change of any session, each time
  // as new objects.
  const status = $derived(session.status);
  let text = $state("");
  let sending = $state(false);
  const busy = $derived(working(session));
  const items = $derived(details ? shownItems(details, session.name) : []);
  // Its dots while it works, but not under a call already showing its own.
  const last = $derived(items.at(-1));
  const thinking = $derived(busy && !(last?.kind === "tool" && last.state === "running"));
  const ended = $derived(busy ? "" : (details?.turns.at(-1)?.finished_at ?? ""));

  // Again when its status changes: how its task ended comes with it.
  $effect(() => {
    void status;
    untrack(() => loaded.refresh());
  });

  $effect(() => {
    const stopSteps = hub.on(["agent_task_step"], (data) => {
      const taken = data as TaskStepTaken;
      if (taken.thread_id !== threadId || taken.session_id !== session.id || !loaded.data) return;
      const next = withStep(loaded.data, taken.task_id, taken.index, taken.step);
      if (next) loaded.data = next;
      else loaded.refresh();
    });
    const stopChanges = hub.on(["tasks_beside"], () => loaded.refresh());
    const stopReconnect = hub.onReconnect(() => loaded.refresh());
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
      loaded.refresh();
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
</script>

<section class="session" aria-label={session.title}>
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
    <div class="composer" class:multiline={text.includes("\n") || text.length > 80}>
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
    <TaskStatus {session} {ended} />
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
  /* The box as the conversation's message box (Composer): the same room around it, height, padding and font. */
  .box {
    padding: 6px 0 0;
  }
  .composer {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 6px 3px 8px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-full);
    background: var(--color-bg-hover-ghost);
    transition: border-color 0.12s ease;
  }
  .composer.multiline {
    border-radius: 16px;
    align-items: flex-end;
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
    padding: 4px;
    max-height: 140px;
    field-sizing: content;
  }
  textarea::placeholder {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
</style>
