<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { carriesFiles, droppedFiles } from "$lib/chat/dropped";
  import { startGetToKnowYou } from "$lib/chat/getToKnowYou";
  import { finalReply } from "$lib/chat/transcript";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { Player, speaksReply } from "$lib/speech";
  import ApprovalModal from "./ApprovalModal.svelte";
  import Composer from "./Composer.svelte";
  import HelpModal from "./HelpModal.svelte";
  import Thread from "./Thread.svelte";

  // Commands that open a tab of the settings page.
  const SETTINGS_TABS: Record<string, string> = {
    "/settings": "general",
    "/startup": "general",
    "/websearch": "general",
    "/audio": "audio",
  };

  const { client, notices, chat } = useDaemon();
  const snapshot = external(chat.subscribe, chat.getSnapshot);
  const name = resource((c) => c.identity.name(), ["settings"]);
  const speech = resource((c) => c.speech.settings(), ["settings"]);
  const player = new Player();
  let help = $state(false);
  let draft = $state("");
  let attached = $state<File[]>([]);
  // Drags enter and leave every element they pass over; the chat is under a drag while this is above 0.
  let dragging = $state(0);
  const streaming = $derived(snapshot.current.transcript.streaming !== null);

  /** Sends, then reads the answer aloud when Settings → Audio says so. */
  async function send(text: string, files: File[]): Promise<void> {
    player.stop();
    await chat.send(text, files);
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
    attached = [...attached, ...files];
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

  function command(name: string, arg: string): void {
    if (name in SETTINGS_TABS) {
      void goto(`${resolve("/settings")}?tab=${SETTINGS_TABS[name]}`);
      return;
    }
    switch (name) {
      case "/new":
        return void chat.startNew();
      case "/home":
        return void chat.goHome();
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
      case "/get-to-know-me":
        return void startGetToKnowYou(chat);
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
    thinking={(snapshot.current.busy || snapshot.current.mirroring) && !streaming}
    name={name.data || "the assistant"}
    onsuggest={(text) => (draft = text)}
  />
  <Composer
    bind:text={draft}
    bind:files={attached}
    busy={snapshot.current.busy}
    running={snapshot.current.busy || snapshot.current.mirroring}
    onsend={send}
    onstop={() => chat.stop()}
    oncommand={command}
  />
  {#if dragging > 0}<div class="drop-hint" aria-hidden="true">Drop files to attach them</div>{/if}
</section>

{#if snapshot.current.approval}
  <ApprovalModal approval={snapshot.current.approval} onanswer={(d) => chat.answer(d)} />
{/if}
{#if help}<HelpModal onclose={() => (help = false)} />{/if}

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
</style>
