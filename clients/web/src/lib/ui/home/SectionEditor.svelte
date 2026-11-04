<script lang="ts">
  import type { HomeSection } from "$lib/api/types";
  import { MAX_COLUMNS } from "$lib/home";
  import { t } from "$lib/i18n.svelte";
  import Modal from "../Modal.svelte";
  import Toggle from "../Toggle.svelte";

  type Props = {
    // null for a new section.
    section: HomeSection | null;
    // The installed plugins with tools, to pick from.
    plugins: string[];
    // Those that list their day for lo9i: a section of one of them shows that list, without the model, unless it asks for
    // the model.
    listing: string[];
    // Why the last save was refused.
    error: string;
    onsave: (section: HomeSection) => void;
    onclose: () => void;
    /** For a new section, the cards built by code that Home doesn't have (Conversations, Open loops): each says what it
     * is and adds it instead. */
    offers?: Array<{ id: string; text: string; add: () => void }>;
  };
  let { section, plugins, listing, error, onsave, onclose, offers = [] }: Props = $props();

  // svelte-ignore state_referenced_locally
  let title = $state(section?.title ?? "");
  // svelte-ignore state_referenced_locally
  let prompt = $state(section?.prompt ?? "");
  // svelte-ignore state_referenced_locally
  let picked = $state<string[]>([...(section?.plugins ?? [])]);
  // svelte-ignore state_referenced_locally
  let columns = $state(section?.columns ?? 0);
  // svelte-ignore state_referenced_locally
  let useModel = $state(section?.use_model ?? false);
  // The plugin whose own list it can show: its one plugin, when that lists its day.
  const listed = $derived(picked.length === 1 && listing.includes(picked[0]) ? picked[0] : null);
  const widths = Array.from({ length: MAX_COLUMNS }, (_, i) => i + 1);
  // A plugin the section names that isn't installed stays listed, so saving doesn't drop it unseen.
  const choices = $derived([...new Set([...plugins, ...picked])].sort());

  function toggle(name: string, on: boolean): void {
    picked = on ? [...picked, name] : picked.filter((p) => p !== name);
  }

  function save(): void {
    onsave({ id: section?.id ?? "", title, prompt, plugins: picked, columns, coded: section?.coded ?? false, use_model: useModel });
  }
</script>

<Modal
  title={section ? t("home.editTitle", { title: section.title }) : t("home.newSection")}
  description={t("home.editorDescription")}
  width={600}
  {onclose}
>
  {#each offers as offer (offer.id)}
    <div class="offer">
      <p class="text-meta">{offer.text}</p>
      <button class="btn btn--neutral btn--sm" onclick={offer.add}>{t("homeConversations.add")}</button>
    </div>
  {/each}
  <label class="field">
    <span class="micro-label">{t("home.title")}</span>
    <input class="input" bind:value={title} placeholder={t("home.titlePlaceholder")} />
  </label>
  {#if section?.coded}
    <!-- Built by code, not by the model: what it shows and the plugins it reads are the code's. -->
    <div class="field">
      <span class="micro-label">{t("home.shows")}</span>
      <p class="text-meta">{section.prompt}</p>
      <p class="text-caption">{t("home.builtByCode")}</p>
    </div>
  {:else}
    <label class="field">
      <span class="micro-label">{t("home.what")}</span>
      <textarea class="input" rows="7" bind:value={prompt} placeholder={t("home.whatPlaceholder")}></textarea>
    </label>
    <fieldset class="field">
      <legend class="micro-label">{t("home.plugins")}</legend>
      {#if choices.length === 0}
        <p class="text-meta">{t("home.noPlugins")}</p>
      {:else}
        <div class="plugins">
          {#each choices as name (name)}
            <label class="plugin">
              <input type="checkbox" checked={picked.includes(name)} onchange={(e) => toggle(name, e.currentTarget.checked)} />
              {name}
              {#if !plugins.includes(name)}<span class="text-caption">{t("home.notInstalled")}</span>{/if}
            </label>
          {/each}
        </div>
        <p class="text-meta">{t("home.nonePicked")}</p>
      {/if}
    </fieldset>
    {#if listed}
      <div class="field">
        <div class="switch">
          <span class="text-label">{t("home.useModel")}</span>
          <Toggle checked={useModel} label={t("home.useModel")} onchange={(on) => (useModel = on)} />
        </div>
        <span class="text-caption">{useModel ? t("home.useModelOn") : t("home.useModelOff", { plugin: listed })}</span>
      </div>
    {/if}
  {/if}
  <label class="field">
    <span class="micro-label">{t("home.width")}</span>
    <select class="input" bind:value={columns}>
      <option value={0}>{t("home.automatic")}</option>
      {#each widths as n (n)}
        <option value={n}>{t("home.columns", { count: n })}</option>
      {/each}
    </select>
    <span class="text-caption">{t("home.widthHint")}</span>
  </label>
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost btn--sm" onclick={onclose}>{t("common.cancel")}</button>
    <button class="btn btn--primary btn--sm" disabled={!title.trim() || !prompt.trim()} onclick={save}>{t("common.save")}</button>
  {/snippet}
</Modal>

<style>
  .switch {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .offer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 12px;
    margin-bottom: 4px;
    border: 1px dashed var(--color-border);
    border-radius: var(--radius-md);
  }
  .offer p {
    margin: 0;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 0;
    padding: 0;
    border: 0;
  }
  textarea {
    resize: vertical;
  }
  .plugins {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
  }
  .plugin {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--font-size-sm);
  }
  .text-meta {
    margin: 0;
  }
</style>
