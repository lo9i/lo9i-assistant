<script lang="ts">
  import Clock from "@lucide/svelte/icons/clock";
  import X from "@lucide/svelte/icons/x";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { draft } from "$lib/chat/draft.svelte";
  import { carriesFiles, droppedFiles } from "$lib/chat/dropped";
  import { putBack, tellAgent } from "$lib/chat/agentWork";
  import { agentCommands } from "$lib/chat/commands";
  import { startGetToKnowYou } from "$lib/chat/getToKnowYou";
  import { sentTexts } from "$lib/chat/history";
  import { finalReply, toolRunning } from "$lib/chat/transcript";
  import type { ChatController } from "$lib/chat/controller";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { Player, speaksReply } from "$lib/speech";
  import type { Agent } from "$lib/api/types";
  import AgentStatus from "./AgentStatus.svelte";
  import AgentFolderModal from "./AgentFolderModal.svelte";
  import ApprovalModal from "./ApprovalModal.svelte";
  import Composer from "./Composer.svelte";
  import ConversationStats from "./ConversationStats.svelte";
  import ModelStatus from "./ModelStatus.svelte";
  import ContextFuel from "./ContextFuel.svelte";
  import HelpModal from "./HelpModal.svelte";
  import PinnedSkills from "./PinnedSkills.svelte";
  import StatusBar from "./StatusBar.svelte";
  import WorkingStatus from "./WorkingStatus.svelte";
  import Thread from "./Thread.svelte";

  // Commands that open a tab of the settings page.
  const SETTINGS_TABS: Record<string, string> = {
    "/settings": "general",
    "/startup": "general",
    "/websearch": "general",
    "/audio": "audio",
  };

  const { client, notices, chats } = useDaemon();
  // The open conversation shown; the sidebar picks it.
  const snapshot = external(chats.subscribe, () => chats.current.getSnapshot());
  // A snapshot comes with every update of the transcript; what's loaded for the conversation is loaded again only
  // when it's another one.
  const threadId = $derived(snapshot.current.threadId);
  const name = resource((c) => c.identity.name(), ["settings"]);
  const speech = resource((c) => c.speech.settings(), ["settings"]);
  const pinned = resource((c) => c.conversations.pinned(threadId), ["pinned_skills"]);
  // Plugins can bring agents a conversation is handed to (/claude); the one this conversation is with.
  const agents = resource((c) => c.conversations.agents(), ["mcp"]);
  const handoff = resource((c) => c.conversations.agent(threadId), ["handoffs"]);
  const extra = $derived(agentCommands(agents.data ?? []));
  const player = new Player();
  let help = $state(false);
  // The agent /claude alone picks a folder for.
  let picking = $state<Agent | null>(null);
  // Drags enter and leave every element they pass over; the chat is under a drag while this is above 0.
  let dragging = $state(0);
  const streaming = $derived(snapshot.current.transcript.streaming !== null);
  const inInbox = $derived(threadId === snapshot.current.inboxId);
  // The agent the conversation is handed to is working on its last message: what's typed goes to it meanwhile.
  const agentWorking = $derived(!!handoff.data && (snapshot.current.busy || snapshot.current.mirroring));

  // Each conversation keeps its own unsent text and files.
  $effect.pre(() => {
    draft.thread = threadId;
  });

  /** Sends, then reads the answer aloud when Settings → Audio says so. */
  async function send(text: string, files: File[]): Promise<void> {
    player.stop();
    const chat = chats.current;
    await chat.send(text, files);
    await speak(chat, files);
  }

  /** Reads `chat`'s answer to a message with `files` aloud when Settings → Audio says so. */
  async function speak(chat: ChatController, files: File[]): Promise<void> {
    const reply = finalReply(chat.getSnapshot().transcript);
    if (
      !reply ||
      !speaksReply(
        speech.data?.spoken_replies,
        files.some((f) => f.type.startsWith("audio/")),
      )
    )
      return;
    try {
      await player.speak(reply, (part) => client.speech.speak(part));
    } catch (e) {
      notices.report(e);
    }
  }

  // Messages written while a reply runs wait in the conversation's queue, each going out when the one before
  // finishes; so do the ones the inbox sends on to it meanwhile.
  function enqueue(text: string, files: File[]): void {
    chats.current.queue(text, files, (chat) => speak(chat, files));
  }
  function unqueue(index: number): void {
    const item = chats.current.unqueue(index);
    if (item && !draft.text.trim()) {
      draft.text = item.text;
      draft.files = item.files;
    }
  }

  /** Passes a message and its files on to the working agent; what it can't take goes back in the box. */
  async function steer(text: string, files: File[]): Promise<void> {
    const taken = await tellAgent(() => client.conversations.messageAgent(threadId, text, files), notices);
    if (!taken) putBack(draft, text, files);
  }

  function dragenter(e: DragEvent): void {
    if (!carriesFiles(e.dataTransfer)) return;
    e.preventDefault();
    dragging += 1;
  }

  function dragover(e: DragEvent): void {
    if (!carriesFiles(e.dataTransfer)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
  }

  function drop(e: DragEvent): void {
    dragging = 0;
    if (!e.dataTransfer || !carriesFiles(e.dataTransfer)) return;
    e.preventDefault();
    const { files, folders } = droppedFiles(e.dataTransfer);
    draft.files = [...draft.files, ...files];
    if (folders) notices.notify("Folders can't be attached; drop the files in them instead.", "warning");
  }

  async function rename(value: string): Promise<void> {
    if (!value) return notices.notify("Usage: /name <name>", "warning");
    try {
      notices.notify(`Renamed to ${await client.identity.rename(value)}.`);
    } catch (e) {
      notices.report(e);
    }
  }

  async function pin(skill: string): Promise<void> {
    if (!skill) return notices.notify("Usage: /pin <skill>", "warning");
    try {
      await client.conversations.pin(threadId, skill);
      notices.notify(`Pinned ${skill} to this conversation. It takes effect from your next message.`);
    } catch (e) {
      notices.report(e);
    }
  }

  async function unpin(skill: string): Promise<void> {
    if (!skill) return notices.notify("Usage: /unpin <skill>", "warning");
    try {
      await client.conversations.unpin(threadId, skill);
      notices.notify(`Unpinned ${skill}. It takes effect from your next message.`);
    } catch (e) {
      notices.report(e);
    }
  }

  /** `/claude <folder>` hands the conversation to the agent, `/claude off` back; alone it picks the folder. */
  async function agentCommand(name: string, arg: string): Promise<void> {
    const agent = (agents.data ?? []).find((a) => `/${a.command}` === name);
    if (!agent) return;
    if (arg === "off") {
      try {
        await client.conversations.takeBack(threadId);
        notices.notify("The assistant answers again from your next message.");
      } catch (e) {
        notices.report(e);
      }
    } else if (arg) {
      await handTo(agent, arg);
    } else {
      picking = agent;
    }
  }

  /** The inbox sends every message on, so in it the agent gets a new conversation. */
  async function handTo(agent: Agent, folder: string): Promise<void> {
    try {
      if (inInbox) await chats.startNew();
      const to = await client.conversations.handTo(chats.current.getSnapshot().threadId, agent.command, folder);
      notices.notify(`${to.name} answers from your next message, working in ${to.folder}. /${agent.command} off goes back.`);
    } catch (e) {
      notices.report(e);
    }
  }

  function picked(folder: string | null): void {
    const agent = picking;
    picking = null;
    if (agent && folder) void handTo(agent, folder);
  }

  function command(name: string, arg: string): void {
    if (extra.some((c) => c.name === name)) {
      void agentCommand(name, arg);
      return;
    }
    if (name in SETTINGS_TABS) {
      void goto(`${resolve("/settings")}?tab=${SETTINGS_TABS[name]}`);
      return;
    }
    switch (name) {
      case "/new":
        return void chats.startNew();
      case "/inbox":
        return void chats.goInbox();
      case "/notifications":
        return void goto(resolve("/notifications"));
      case "/move":
        return void chats.move("");
      case "/conversations":
        return void goto(resolve("/conversations"));
      case "/sessions":
        return void goto(resolve("/sessions"));
      case "/jobs":
        return void goto(resolve("/jobs"));
      case "/plugins":
        return void goto(resolve("/plugins"));
      case "/mcp":
        return void goto(resolve("/mcp"));
      case "/skills":
        return void goto(resolve("/skills"));
      case "/usage":
        return void goto(resolve("/usage"));
      case "/profile":
        return void goto(resolve("/memory"));
      case "/name":
        return void rename(arg);
      case "/pin":
        return void pin(arg);
      case "/unpin":
        return void unpin(arg);
      case "/get-to-know-me":
        return void startGetToKnowYou(chats);
      case "/help":
        help = true;
        return;
      default:
        notices.notify(`Unknown command ${name}. Type / to see the commands.`, "warning");
    }
  }
</script>

<!-- A file dropped beside the chat would make the browser open it, leaving the app. -->
<svelte:window
  ondragover={(e) => carriesFiles(e.dataTransfer) && e.preventDefault()}
  ondrop={(e) => carriesFiles(e.dataTransfer) && e.preventDefault()}
/>

<section
  class="chat surface--glass"
  class:dragging={dragging > 0}
  aria-label="Conversation"
  ondragenter={dragenter}
  ondragover={dragover}
  ondragleave={() => (dragging = Math.max(0, dragging - 1))}
  ondrop={drop}
>
  <Thread
    items={snapshot.current.transcript.items}
    thinking={(snapshot.current.busy || snapshot.current.mirroring) && !streaming && !toolRunning(snapshot.current.transcript)}
    name={name.data || "the assistant"}
    onsuggest={(text) => (draft.text = text)}
    onmove={inInbox ? (dispatchId) => chats.move(dispatchId) : undefined}
    loadCall={(callId) => client.conversations.toolCall(threadId, callId)}
    loadStep={(callId, index) => client.conversations.toolCallStep(threadId, callId, index)}
  />
  {#if snapshot.current.queued.length}
    <ul class="queued" aria-label="Queued messages">
      {#each snapshot.current.queued as item, i (i)}
        <li>
          <Clock size={12} /><span>{item.text || item.files.map((f) => f.name).join(", ")}</span>
          <!-- One the inbox sent on here can't be taken back: it was already written. -->
          {#if !item.dispatched}
            <button aria-label="Take back" title="Take back to edit" onclick={() => unqueue(i)}><X size={12} /></button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
  <PinnedSkills skills={pinned.data ?? []} onunpin={unpin} />
  <Composer
    bind:text={draft.text}
    bind:files={draft.files}
    sent={sentTexts(snapshot.current.transcript.items)}
    busy={snapshot.current.busy}
    running={snapshot.current.busy || snapshot.current.mirroring}
    onsend={send}
    onqueue={enqueue}
    onstop={() => chats.current.stop()}
    oncommand={command}
    {extra}
    steering={agentWorking && handoff.data ? { agent: handoff.data.name, onsteer: steer } : null}
  />
  <StatusBar>
    <WorkingStatus {threadId} />
    <ConversationStats {threadId} />
    {#if handoff.data}
      <AgentStatus handoff={handoff.data} onback={() => agentCommand(`/${handoff.data?.command}`, "off")} />
    {:else}
      <ModelStatus />
    {/if}
    <span class="fuel-end"><ContextFuel {threadId} /></span>
  </StatusBar>
  {#if dragging > 0}<div class="drop-hint" aria-hidden="true">Drop files to attach them</div>{/if}
</section>

{#if snapshot.current.approval}
  <ApprovalModal approval={snapshot.current.approval} onanswer={(d) => chats.current.answer(d)} />
{/if}
{#if help}<HelpModal onclose={() => (help = false)} {extra} />{/if}
{#if picking}<AgentFolderModal agentName={picking.name} onpick={picked} />{/if}

<style>
  .chat {
    position: relative;
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: 100%;
  }
  .drop-hint {
    position: absolute;
    inset: 8px;
    display: grid;
    place-items: center;
    border: 2px dashed color-mix(in srgb, var(--color-accent) 60%, transparent);
    border-radius: var(--radius-lg, 16px);
    background: color-mix(in srgb, var(--color-accent) 8%, transparent);
    font-weight: 600;
    pointer-events: none;
  }
  .queued {
    list-style: none;
    margin: 0;
    padding: 0 16px;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
  }
  .queued li {
    display: flex;
    align-items: center;
    gap: 6px;
    max-width: 70%;
    padding: 4px 6px 4px 10px;
    border: 1px dashed var(--color-border);
    border-radius: var(--radius-sm);
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
  }
  .queued span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .queued button {
    display: flex;
    border: 0;
    background: none;
    color: inherit;
    cursor: pointer;
    padding: 2px;
  }
  /* The context bar at the status bar's right end. */
  .fuel-end {
    margin-left: auto;
  }
</style>
