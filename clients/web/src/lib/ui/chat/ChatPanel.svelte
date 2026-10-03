<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
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
    "/telegram": "integrations",
    "/slack": "integrations",
    "/email": "integrations",
    "/audio": "audio",
  };

  const { client, notices, chat } = useDaemon();
  const snapshot = external(chat.subscribe, chat.getSnapshot);
  const name = resource((c) => c.identity.name(), ["settings"]);
  const speech = resource((c) => c.speech.settings(), ["settings"]);
  const player = new Player();
  let help = $state(false);
  let draft = $state("");
  const streaming = $derived(snapshot.current.transcript.streaming !== null);

  /** Sends, then reads the answer aloud when Settings → Audio says so. */
  async function send(text: string, files: File[]): Promise<void> {
    player.stop();
    await chat.send(text, files);
    const reply = finalReply(chat.getSnapshot().transcript);
    if (!reply || !speaksReply(speech.data?.spoken_replies, files.some((f) => f.type.startsWith("audio/")))) return;
    try {
      await player.play(await client.speech.speak(reply));
    } catch (e) {
      notices.report(e);
    }
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

<section class="chat surface--glass">
  <Thread
    items={snapshot.current.transcript.items}
    thinking={(snapshot.current.busy || snapshot.current.mirroring) && !streaming}
    name={name.data || "the assistant"}
    onsuggest={(text) => (draft = text)}
  />
  <Composer
    bind:text={draft}
    busy={snapshot.current.busy}
    running={snapshot.current.busy || snapshot.current.mirroring}
    onsend={send}
    onstop={() => chat.stop()}
    oncommand={command}
  />
</section>

{#if snapshot.current.approval}
  <ApprovalModal approval={snapshot.current.approval} onanswer={(d) => chat.answer(d)} />
{/if}
{#if help}<HelpModal onclose={() => (help = false)} />{/if}

<style>
  .chat {
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: 100%;
  }
</style>
