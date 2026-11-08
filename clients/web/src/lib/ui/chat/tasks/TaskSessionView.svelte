<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import { untrack } from "svelte";
  import type { TaskSession, TaskSessionDetails, TaskStepTaken } from "$lib/api/types";
  import { shownItems, withStep, working } from "$lib/chat/codingTasks";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
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
  let details = $state<TaskSessionDetails | null>(null);
  let error = $state("");
  let text = $state("");
  let sending = $state(false);
  const busy = $derived(working(session));
  const items = $derived(details ? shownItems(details, session.name) : []);
  // Its dots while it works, but not under a call already showing its own.
  const last = $derived(items.at(-1));
  const thinking = $derived(busy && !(last?.kind === "tool" && last.state === "running"));
  const ended = $derived(busy ? "" : (details?.turns.at(-1)?.finished_at ?? ""));

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
</style>
