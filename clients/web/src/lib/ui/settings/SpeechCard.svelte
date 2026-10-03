<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  const MODEL_NOTES: Record<string, string> = {
    tiny: "fastest, least accurate",
    base: "fast",
    small: "balanced",
    medium: "slower, more accurate",
    "large-v3-turbo": "most accurate, slowest",
  };

  const { client, notices } = useDaemon();
  const loaded = resource((c) => c.speech.settings(), ["settings"]);
  const s = $derived(loaded.data);
  let model = $state("");
  let languages = $state<string[]>([]);
  let decoding = $state<"accurate" | "fast">("accurate");
  let error = $state("");

  // The form starts from the saved settings, and again after they change elsewhere.
  $effect(() => {
    if (s) {
      model = s.model;
      languages = [...s.languages];
      decoding = s.decoding;
    }
  });

  const changed = $derived(!!s && (model !== s.model || languages.join() !== s.languages.join() || decoding !== s.decoding));

  function toggle(code: string, on: boolean): void {
    languages = on ? [...languages, code] : languages.filter((c) => c !== code);
  }

  async function save(): Promise<void> {
    try {
      await client.speech.change(model, languages, decoding);
      error = "";
      notices.notify("Saved. Used from the next voice message.");
    } catch (e) {
      error = describe(e);
    }
    loaded.reload();
  }
</script>

<SettingsCard id="speech" title="Speech to text" sub="How voice messages from any channel are transcribed, on this host.">
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else}
    <label class="field">
      <span class="micro-label">Model</span>
      <select class="input" bind:value={model}>
        {#each s.models as m (m)}
          <option value={m}>{m} ({MODEL_NOTES[m] ?? ""})</option>
        {/each}
      </select>
      <span class="text-caption">A model is downloaded the first time it's used, so that voice message takes longer.</span>
    </label>
    <label class="field">
      <span class="micro-label">Transcription</span>
      <select class="input" bind:value={decoding}>
        <option value="accurate">Accurate: weighs 5 candidate sentences</option>
        <option value="fast">Fast: takes the likeliest word each time, about twice as fast</option>
      </select>
      <span class="text-caption"
        >On a slow computer, Fast with a smaller model answers much sooner. Accurate helps most with noisy or unclear audio.</span
      >
    </label>
    <fieldset class="field">
      <legend class="micro-label">Languages</legend>
      <div class="languages">
        {#each s.language_options as option (option.code)}
          <label class="check">
            <input
              type="checkbox"
              checked={languages.includes(option.code)}
              onchange={(e) => toggle(option.code, e.currentTarget.checked)}
            />
            {option.name}
          </label>
        {/each}
      </div>
      <span class="text-caption">Each voice message is detected as one of these. Fewer languages, fewer mistakes.</span>
    </fieldset>
    <div class="row">
      <button class="btn btn--primary" disabled={!changed || languages.length === 0} onclick={save}>Save</button>
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
  .languages {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 6px 12px;
  }
  .check {
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
</style>
