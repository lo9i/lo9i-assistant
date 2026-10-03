<script lang="ts">
  import Play from "@lucide/svelte/icons/play";
  import type { SpeechStatus } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import { Player } from "$lib/speech";
  import SettingsCard from "../Card.svelte";

  type Mode = SpeechStatus["spoken_replies"];
  const MODES: { id: Mode; label: string }[] = [
    { id: "off", label: "Off" },
    { id: "voice", label: "When I send a voice message" },
    { id: "always", label: "Always" },
  ];
  const SAMPLES: Record<string, string> = {
    Spanish: "Hola, así va a sonar cuando te responda.",
    "Portuguese (BR)": "Olá, é assim que vou soar quando responder.",
    French: "Bonjour, voici ma voix quand je te réponds.",
    Italian: "Ciao, questa è la mia voce quando ti rispondo.",
    Hindi: "नमस्ते, जवाब देते समय मेरी आवाज़ ऐसी होगी।",
  };

  const { client } = useDaemon();
  const loaded = resource((c) => c.speech.settings(), ["settings"]);
  const s = $derived(loaded.data);
  const player = new Player();
  const groups = $derived(Object.groupBy(s?.voice_options ?? [], (v) => v.language));
  let trying = $state(false);
  let error = $state("");

  async function change(mode: Mode, voice: string): Promise<void> {
    try {
      await client.speech.changeReplies(mode, voice);
      error = "";
    } catch (e) {
      error = describe(e);
    }
    loaded.reload();
  }

  /** The first try downloads the voice model on the host, so it can take a minute. */
  async function tryVoice(voice: string): Promise<void> {
    const language = s?.voice_options.find((v) => v.id === voice)?.language ?? "";
    trying = true;
    try {
      await player.play(await client.speech.speak(SAMPLES[language] ?? "Hi, this is how I'll sound when I reply.", voice));
      error = "";
    } catch (e) {
      error = describe(e);
    } finally {
      trying = false;
    }
  }
</script>

<SettingsCard id="spoken-replies" title="Spoken replies" sub="Replies read aloud on this host, in the web chat and as Telegram voice notes.">
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else}
    <fieldset class="field">
      <legend class="micro-label">Speak replies</legend>
      {#each MODES as m (m.id)}
        <label class="choice">
          <input
            type="radio"
            name="spoken-replies"
            checked={s.spoken_replies === m.id}
            onchange={() => change(m.id, s.voice)}
          />
          {m.label}
        </label>
      {/each}
    </fieldset>
    <div class="field">
      <span class="micro-label">Voice</span>
      <div class="row">
        <select class="input" value={s.voice} onchange={(e) => change(s.spoken_replies, e.currentTarget.value)} aria-label="Voice">
          {#each Object.entries(groups) as [language, voices] (language)}
            <optgroup label={language}>
              {#each voices ?? [] as v (v.id)}<option value={v.id}>{v.name} ({language})</option>{/each}
            </optgroup>
          {/each}
        </select>
        <button class="btn btn--neutral" disabled={trying} onclick={() => tryVoice(s.voice)}>
          <Play size={14} />{trying ? "Speaking…" : "Try"}
        </button>
      </div>
      <span class="text-caption">A voice speaks one language. The first reply downloads the voice model (about 115 MB).</span>
    </div>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SettingsCard>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding: 0;
    border: 0;
  }
  legend {
    padding: 0;
    margin-bottom: 8px;
  }
  .choice {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--font-size-sm);
    cursor: pointer;
  }
  .row {
    display: flex;
    gap: 8px;
  }
  .row select {
    flex: 1;
  }
  .row button {
    flex: none;
  }
</style>
