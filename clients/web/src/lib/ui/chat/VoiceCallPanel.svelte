<script lang="ts">
  import AudioLines from "@lucide/svelte/icons/audio-lines";
  import Mic from "@lucide/svelte/icons/mic";
  import MicOff from "@lucide/svelte/icons/mic-off";
  import PhoneOff from "@lucide/svelte/icons/phone-off";
  import X from "@lucide/svelte/icons/x";
  import { resolve } from "$app/paths";
  import { t } from "$lib/i18n.svelte";
  import { shownLines } from "$lib/voiceCall";
  import type { VoiceCall } from "$lib/voiceCall.svelte";

  // Above the message box while a live voice call is on in the conversation: how it goes, the latest lines as they're
  // spoken (the conversation keeps each once it's said), mute and hang up. Without an OpenAI key, where to add one.
  type Props = {
    call: VoiceCall;
    /** The assistant's name, for its lines and while the voice asks it. */
    name: string;
    /** The call button was pressed with no OpenAI key set. */
    needsKey: boolean;
    onhangup: () => void;
    onclose: () => void;
  };
  let { call, name, needsKey, onhangup, onclose }: Props = $props();

  const lines = $derived(shownLines(call.transcript));
  const status = $derived(
    call.state === "connecting"
      ? t("voiceCall.connecting")
      : call.muted
        ? t("voiceCall.muted")
        : call.transcript.asking
          ? t("voiceCall.asking", { name })
          : call.transcript.listening
            ? t("voiceCall.listening")
            : t("voiceCall.live"),
  );
</script>

{#if needsKey}
  <div class="call notice" role="status">
    <p>{t("voiceCall.needsKey")}</p>
    <a class="btn btn--primary btn--sm" href={`${resolve("/settings")}?tab=audio#voice-calls`}>{t("voiceCall.addKey")}</a>
    <button class="close" aria-label={t("common.close")} title={t("common.close")} onclick={onclose}><X size={14} /></button>
  </div>
{:else if call.state !== "idle"}
  <div class="call" role="region" aria-label={t("voiceCall.title")}>
    <div class="head">
      <span class="dot" class:connecting={call.state === "connecting"}></span>
      <AudioLines size={14} />
      <span class="status" aria-live="polite">{status}</span>
      <button class="btn btn--ghost btn--sm" aria-pressed={call.muted} onclick={() => call.toggleMute()}>
        {#if call.muted}<MicOff size={14} />{t("voiceCall.unmute")}{:else}<Mic size={14} />{t("voiceCall.mute")}{/if}
      </button>
      <button class="btn btn--danger btn--sm" onclick={onhangup}><PhoneOff size={14} />{t("voiceCall.hangUp")}</button>
    </div>
    {#if lines.length}
      <ol class="lines">
        {#each lines as line (line.id)}
          <li class={line.who} class:speaking={!line.done}>
            <span class="who">{line.who === "user" ? t("voiceCall.you") : name}</span>{line.text}
          </li>
        {/each}
      </ol>
    {/if}
  </div>
{:else if call.error}
  <div class="call notice" role="alert">
    <p class="error-text">{t("voiceCall.failed", { error: call.error })}</p>
    <button class="close" aria-label={t("common.close")} title={t("common.close")} onclick={onclose}><X size={14} /></button>
  </div>
{/if}

<style>
  .call {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 8px 16px 0;
    padding: 10px 12px;
    border: 1px solid color-mix(in srgb, var(--color-accent) 45%, transparent);
    border-radius: var(--radius-md, 12px);
    background: color-mix(in srgb, var(--color-accent) 7%, transparent);
    font-size: var(--font-size-sm);
  }
  .notice {
    flex-direction: row;
    align-items: center;
    gap: 12px;
  }
  .notice p {
    flex: 1;
    margin: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .status {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }
  .dot {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--color-danger, #e5484d);
    animation: pulse 1.4s ease-in-out infinite;
  }
  .dot.connecting {
    background: var(--color-text-faint);
  }
  @keyframes pulse {
    50% {
      opacity: 0.35;
    }
  }
  .lines {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 9em;
    overflow-y: auto;
  }
  .lines li {
    color: var(--color-text-primary);
  }
  .lines li.speaking {
    color: var(--color-text-muted);
  }
  .who {
    margin-right: 6px;
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .voice .who {
    color: var(--color-accent);
  }
  .close {
    display: flex;
    flex: none;
    border: 0;
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
    padding: 2px;
  }
  @media (prefers-reduced-motion: reduce) {
    .dot {
      animation: none;
    }
  }
</style>
