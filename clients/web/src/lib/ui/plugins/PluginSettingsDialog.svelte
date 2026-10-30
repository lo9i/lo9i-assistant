<script lang="ts">
  import { onMount } from "svelte";
  import SecretInput from "../SecretInput.svelte";
  import type { PluginFieldValue, PluginSettings } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { settingsChange } from "$lib/pluginSettings";
  import Modal from "../Modal.svelte";

  // An installed plugin's settings: the values its fields were given, changed without installing it again. A
  // secret's value never comes here: it shows as saved, kept when left empty, and an optional one can be cleared.
  // Its check runs before anything is saved; what it says shows here. From its details on the Plugins page.
  type Props = { plugin: string; onclose: (saved?: boolean) => void };
  let { plugin, onclose }: Props = $props();
  const { client } = useDaemon();

  let settings = $state<PluginSettings | null>(null);
  // What's typed, by field key: a field not secret starts with its value, a secret one empty.
  let values = $state<Record<string, string>>({});
  // Secret fields to remove.
  let cleared = $state(new Set<string>());
  let busy = $state(false);
  let error = $state("");

  onMount(() => void load());

  async function load(): Promise<void> {
    try {
      const read = await client.mcp.pluginSettings(plugin);
      values = Object.fromEntries(read.fields.map((f) => [f.key, f.secret ? "" : f.value]));
      settings = read;
    } catch (e) {
      error = describe(e);
    }
  }

  async function save(): Promise<void> {
    if (!settings) return;
    const change = settingsChange(settings.fields, values, cleared);
    if (!change) return onclose();
    busy = true;
    error = "";
    try {
      await client.mcp.changePluginSettings(plugin, change);
      onclose(true);
    } catch (e) {
      error = describe(e);
    } finally {
      busy = false;
    }
  }

  function toggleClear(key: string): void {
    const next = new Set(cleared);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    cleared = next;
    values[key] = "";
  }

  function secretHint(f: PluginFieldValue): string {
    if (cleared.has(f.key)) return t("pluginSettings.willBeRemoved");
    return f.set ? t("pluginSettings.savedKeep") : t("pluginSettings.notSet");
  }

  /** "t.me/BotFather" for a help link: the address without its scheme reads better. */
  function shortLink(url: string): string {
    return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
  }
</script>

<Modal
  title={t("pluginSettings.title", { name: plugin })}
  description={t("pluginSettings.description")}
  width={560}
  onclose={() => onclose()}
>
  {#if settings === null && !error}
    <p class="text-meta">{t("common.loading")}</p>
  {:else if settings}
    <div class="form">
      {#if settings.check}<p class="text-label">{t("pluginSettings.checks")}</p>{/if}
      {#each settings.fields as f (f.key)}
        <label class="field">
          <span class="field-label"
            >{f.label}{#if f.optional}<span class="text-caption"> · {t("pluginSettings.optional")}</span>{/if}</span
          >
          {#if f.secret}
            <div class="secret-row">
              <SecretInput label={f.label} bind:value={values[f.key]} placeholder={secretHint(f)} />
              {#if f.optional && f.set}
                <button type="button" class="btn btn--ghost btn--sm" aria-pressed={cleared.has(f.key)} onclick={() => toggleClear(f.key)}
                  >{cleared.has(f.key) ? t("pluginSettings.keep") : t("pluginSettings.clear")}</button
                >
              {/if}
            </div>
          {:else}
            <input class="input" bind:value={values[f.key]} required={!f.optional} autocomplete="off" />
          {/if}
          {#if f.help}<span class="text-caption"
              >{t("install.getItAt")} <a href={f.help} target="_blank" rel="noreferrer">{shortLink(f.help)}</a></span
            >{/if}
        </label>
      {/each}
    </div>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onclose()}>{t("common.cancel")}</button>
    {#if settings}
      <button class="btn btn--primary" disabled={busy} onclick={save}
        >{busy ? (settings.check ? t("pluginSettings.checking") : t("pluginSettings.saving")) : t("common.save")}</button
      >
    {:else if error}
      <button class="btn btn--primary" onclick={() => ((error = ""), void load())}>{t("app.tryAgain")}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .form {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .field {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
  }
  .field-label {
    font-weight: 600;
  }
  .secret-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .secret-row :global(.secret) {
    flex: 1;
  }
  p {
    margin: 0;
  }
</style>
