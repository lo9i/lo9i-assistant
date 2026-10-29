<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import AudioLines from "@lucide/svelte/icons/audio-lines";
  import Send from "@lucide/svelte/icons/send-horizontal";
  import Volume2 from "@lucide/svelte/icons/volume-2";
  import { finalReply } from "$lib/chat/transcript";
  import { external, useDaemon } from "$lib/daemon.svelte";
  import { t, type Key } from "$lib/i18n.svelte";
  import { Recorder } from "$lib/microphone.svelte";
  import { Player } from "$lib/speech";
  import { clock, phase, type Phase } from "$lib/voice";
  import ApprovalModal from "../chat/ApprovalModal.svelte";
  import FloatingButton from "./FloatingButton.svelte";
  import QuickPanel from "./QuickPanel.svelte";
  import { quickPanel } from "./openPanel.svelte";

  // Talks with the assistant from any page: each recording is written in the inbox, which sends it on to
  // its conversation, and the reply is read aloud.
  const { client, notices, voice } = useDaemon();
  const snapshot = external(voice.subscribe, voice.getSnapshot);
  const recorder = new Recorder();
  let speaking = $state(false);
  const player = new Player(() => (speaking = false));
  let preparingSpeech = $state(false);
  // Counts turns, so a reply still being read aloud is dropped once the user moves on.
  let turn = 0;
  let now = $state(Date.now());

  const current = $derived(phase({ recording: recorder.recording, busy: snapshot.current.busy, preparingSpeech, speaking }));
  const reply = $derived(finalReply(snapshot.current.transcript));
  const LABELS: Record<Phase, Key> = {
    idle: "quick.talk",
    listening: "quick.send",
    thinking: "quick.stop",
    speaking: "quick.stopSpeaking",
  };

  $effect(() => {
    if (!recorder.recording) return;
    const timer = setInterval(() => (now = Date.now()), 250);
    return () => clearInterval(timer);
  });

  function press(): void {
    if (current === "idle") void listen();
    else if (current === "listening") void send();
    else if (current === "thinking") void stopThinking();
    else player.stop();
  }

  async function listen(): Promise<void> {
    try {
      await recorder.start();
      now = Date.now();
      quickPanel.open = "voice";
    } catch (e) {
      notices.report(e);
    }
  }

  async function send(): Promise<void> {
    const recording = await recorder.stop();
    const mine = ++turn;
    await voice.write("", [recording]);
    const text = finalReply(voice.getSnapshot().transcript);
    if (text && mine === turn) await speak(text, mine);
  }

  async function speak(text: string, mine: number): Promise<void> {
    preparingSpeech = true;
    try {
      await player.speak(
        text,
        (part) => client.speech.speak(part),
        () => {
          // A newer turn started while the first part was being prepared: leave it silent.
          if (mine !== turn) return player.stop();
          preparingSpeech = false;
          speaking = true;
        },
      );
    } catch {
      // Speech output isn't set up (or failed): the reply is still shown.
      speaking = false;
      notices.notify(text);
    } finally {
      preparingSpeech = false;
    }
  }

  async function stopThinking(): Promise<void> {
    turn++;
    if (snapshot.current.busy) await voice.stop();
  }

  function close(): void {
    turn++;
    recorder.cancel();
    player.stop();
    if (quickPanel.open === "voice") quickPanel.open = null;
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === "Escape" && recorder.recording) recorder.cancel();
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if quickPanel.open === "voice"}
  <QuickPanel
    title={t("quick.voice")}
    chat={snapshot.current}
    reply={current === "listening" ? "" : reply}
    hint={current === "listening" ? "" : t("quick.voiceHint")}
    onstop={() => void stopThinking()}
    onclose={close}
  >
    {#if current === "listening"}
      <p class="status">
        <span class="dot"></span>{t("quick.listening", { elapsed: clock(now - recorder.startedAt) })}
      </p>
    {/if}
  </QuickPanel>
{/if}
<FloatingButton label={t(LABELS[current])} tone={current} onclick={press}>
  {#if current === "listening"}
    <Send size={18} />
  {:else if current === "thinking"}
    <LoaderCircle size={18} class="spin" />
  {:else if current === "speaking"}
    <Volume2 size={18} />
  {:else}
    <AudioLines size={18} />
  {/if}
</FloatingButton>

{#if snapshot.current.approval}
  <ApprovalModal approval={snapshot.current.approval} onanswer={(d) => voice.answer(d)} />
{/if}

<style>
  .status {
    margin: 0;
    color: var(--color-text-muted);
  }
  .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    margin-right: 8px;
    border-radius: 50%;
    background: var(--color-danger);
  }
</style>
