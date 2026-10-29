<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { language, t, type LanguageChoice } from "$lib/i18n.svelte";
  import SettingsCard from "../Card.svelte";

  // The language of the apps' own text, kept by the daemon for every app; auto follows this browser's. The
  // assistant's replies follow the language written to it, whatever this says.
  const { client, notices } = useDaemon();
  const saved = resource((c) => c.language.get(), ["settings"]);

  async function change(choice: LanguageChoice): Promise<void> {
    language.use(choice);
    try {
      await client.language.set(choice);
    } catch (e) {
      notices.report(e);
    }
    saved.reload();
  }
</script>

<SettingsCard id="language" title={t("language.title")} sub={t("language.sub")}>
  {#if saved.data === undefined}
    <p class="text-meta">{saved.error ?? t("common.loading")}</p>
  {:else}
    <label class="field">
      <span class="micro-label">{t("language.label")}</span>
      <select
        class="input"
        value={saved.data.language}
        onchange={(e) => change(e.currentTarget.value as LanguageChoice)}
        aria-label={t("language.label")}
      >
        <option value="auto">{t("language.auto")}</option>
        <option value="en">English</option>
        <option value="es">Español</option>
      </select>
      <span class="text-caption">{t("language.hint")}</span>
    </label>
  {/if}
</SettingsCard>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
</style>
