<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { languageName, t, type Key } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  const MODEL_NOTES: Record<string, Key> = {
    tiny: "speech.tiny",
    base: "speech.base",
    small: "speech.small",
    medium: "speech.medium",
    "large-v3-turbo": "speech.large",
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
      notices.notify(t("speech.saved"));
    } catch (e) {
      error = describe(e);
    }
    loaded.reload();
  }
</script>

<SettingsCard id="speech" title={t("speech.title")} sub={t("speech.sub")}>
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
  {:else}
    <label class="field">
      <span class="micro-label">{t("speech.model")}</span>
      <select class="input" bind:value={model}>
        {#each s.models as m (m)}
          <option value={m}>{m} ({m in MODEL_NOTES ? t(MODEL_NOTES[m]) : ""})</option>
        {/each}
      </select>
      <span class="text-caption">{t("speech.modelHint")}</span>
    </label>
    <label class="field">
      <span class="micro-label">{t("speech.transcription")}</span>
      <select class="input" bind:value={decoding}>
        <option value="accurate">{t("speech.accurate")}</option>
        <option value="fast">{t("speech.fast")}</option>
      </select>
      <span class="text-caption">{t("speech.decodingHint")}</span>
    </label>
    <fieldset class="field">
      <legend class="micro-label">{t("speech.languages")}</legend>
      <div class="languages">
        {#each s.language_options as option (option.code)}
          <label class="check">
            <input
              type="checkbox"
              checked={languages.includes(option.code)}
              onchange={(e) => toggle(option.code, e.currentTarget.checked)}
            />
            {languageName(option.code)}
          </label>
        {/each}
      </div>
      <span class="text-caption">{t("speech.languagesHint")}</span>
    </fieldset>
    <div class="row">
      <button class="btn btn--primary" disabled={!changed || languages.length === 0} onclick={save}>{t("common.save")}</button>
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
