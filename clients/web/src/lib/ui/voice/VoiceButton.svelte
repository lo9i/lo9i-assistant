<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import AudioLines from "@lucide/svelte/icons/audio-lines";
  import RotateCcw from "@lucide/svelte/icons/rotate-ccw";
  import Send from "@lucide/svelte/icons/send-horizontal";
  import Volume2 from "@lucide/svelte/icons/volume-2";
  import X from "@lucide/svelte/icons/x";
  import { finalReply } from "$lib/chat/transcript";
  import { external, useDaemon } from "$lib/daemon.svelte";
  import { Recorder } from "$lib/microphone.svelte";
  import { Player } from "$lib/speech";
  import { clock, phase, type Phase } from "$lib/voice";
  import ApprovalModal from "../chat/ApprovalModal.svelte";

  // Talks with the assistant from any page, in the voice conversation (kept apart from the chat).
  const { client, notices, voice } = useDaemon();
  const snapshot = external(voice.subscribe, voice.getSnapshot);
  const recorder = new Recorder();
  let speaking = $state(false);
  const player = new Player(() => (speaking = false));
  let preparingSpeech = $state(false);
  // Counts turns, so a reply still being read aloud is dropped once the user moves on.
  let turn = 0;
  let open = $state(false);
  let now = $state(Date.now());

  const current = $derived(phase({ recording: recorder.recording, busy: snapshot.current.busy, preparingSpeech, speaking }));
  const reply = $derived(finalReply(snapshot.current.transcript));
  const LABELS: Record<Phase, string> = {
    idle: "Voice conversation with the assistant",
    listening: "Send",
    thinking: "Stop",
    speaking: "Stop speaking",
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
      open = true;
    } catch (e) {
      notices.report(e);
    }
  }

  async function send(): Promise<void> {
    const recording = await recorder.stop();
    const mine = ++turn;
    await voice.send("", [recording]);
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
    open = false;
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === "Escape" && recorder.recording) recorder.cancel();
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="voice">
  {#if open}
    <section class="bubble surface--glass" aria-live="polite">
      <header>
        <span class="micro-label">Voice</span>
        <div class="actions">
          <button
            class="icon"
            aria-label="New voice conversation"
            title="New voice conversation"
            disabled={current !== "idle"}
            onclick={() => voice.startNew()}
          >
            <RotateCcw size={14} />
          </button>
          <button class="icon" aria-label="Close" title="Close" onclick={close}><X size={14} /></button>
        </div>
      </header>
      {#if current === "listening"}
        <p class="status">
          <span class="dot"></span>Listening {clock(now - recorder.startedAt)}. Tap to send, Esc to cancel.
        </p>
      {:else if current === "thinking" && !reply}
        <p class="status">Thinking…</p>
      {:else if reply}
        <p class="reply">{reply}</p>
      {:else}
        <p class="status">Tap the button and ask for something.</p>
      {/if}
    </section>
  {/if}
  <button class="fab {current}" aria-label={LABELS[current]} title={LABELS[current]} onclick={press}>
    {#if current === "listening"}
      <Send size={12} />
    {:else if current === "thinking"}
      <LoaderCircle size={12} class="spin" />
    {:else if current === "speaking"}
      <Volume2 size={12} />
    {:else}
      <AudioLines size={12} />
    {/if}
  </button>
</div>

{#if snapshot.current.approval}
  <ApprovalModal approval={snapshot.current.approval} onanswer={(d) => voice.answer(d)} />
{/if}

<style>
  /* Floating in the window's bottom right corner, on every page. */
  .voice {
    position: fixed;
    right: 24px;
    bottom: 24px;
    z-index: var(--z-popover);
    display: flex;
  }
  .fab {
    display: grid;
    place-items: center;
    width: 29px;
    height: 29px;
    border: none;
    /* A speech bubble with its tail in the corner: talking with the assistant. */
    border-radius: 15px 15px 4px 15px;
    background: var(--color-action-primary);
    color: var(--color-action-on-primary);
    box-shadow: var(--shadow-popover);
    cursor: pointer;
    transition:
      transform 0.15s ease,
      filter 0.15s ease;
  }
  .fab:hover {
    filter: brightness(0.92);
    transform: translateY(-1px);
  }
  .fab.listening {
    background: var(--color-danger);
    animation: pulse 1.4s ease-in-out infinite;
  }
  .fab :global(.spin) {
    animation: spin 1s linear infinite;
  }
  /* Above the button, in the same corner. */
  .bubble {
    position: fixed;
    right: 24px;
    bottom: 64px;
    z-index: var(--z-popover);
    width: min(360px, calc(100vw - 48px));
    max-height: 50vh;
    overflow-y: auto;
    padding: 12px 16px 16px;
    box-shadow: var(--shadow-popover);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .actions {
    display: flex;
    gap: 4px;
  }
  .icon {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .icon:hover:not(:disabled) {
    background: var(--color-bg-hover-ghost);
  }
  .icon:disabled {
    opacity: 0.4;
    cursor: default;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .status {
    color: var(--color-text-muted);
  }
  .reply {
    white-space: pre-wrap;
  }
  .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    margin-right: 8px;
    border-radius: 50%;
    background: var(--color-danger);
  }
  @keyframes pulse {
    50% {
      box-shadow: 0 0 0 6px color-mix(in srgb, var(--color-danger) 20%, transparent);
    }
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
