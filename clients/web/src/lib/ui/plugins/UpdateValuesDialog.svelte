<script lang="ts">
  import { onMount } from "svelte";
  import SecretInput from "../SecretInput.svelte";
  import type { FoundServer } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { fromRepositories } from "$lib/plugins";
  import Modal from "../Modal.svelte";

  // A plugin whose new version asks for values it wasn't given (its update answered 409): the new version's fields
  // the installed one has no value for, from the listing the update was found in, and the update again with them.
  // `reason`: what the update said, shown when those fields can't be told.
  type Props = { plugin: string; reason: string; onclose: (updated?: boolean) => void };
  let { plugin, reason, onclose }: Props = $props();
  const { client } = useDaemon();

  let fields = $state<FoundServer["fields"] | null>(null);
  let values = $state<Record<string, string>>({});
  let busy = $state(false);
  let error = $state("");

  onMount(() => void load());

  async function load(): Promise<void> {
    try {
      const [listing, installed] = await Promise.all([client.repositories.plugins(true), client.mcp.pluginSettings(plugin)]);
      const found = fromRepositories(listing).plugins.find((p) => p.kind === "server" && p.installed && p.name === plugin);
      const set = new Set(installed.fields.filter((f) => f.set).map((f) => f.key));
      const missing = found?.kind === "server" ? found.server.fields.filter((f) => !set.has(f.key)) : [];
      if (!missing.length) error = reason;
      values = Object.fromEntries(missing.map((f) => [f.key, ""]));
      fields = missing;
    } catch (e) {
      error = describe(e);
    }
  }

  async function update(): Promise<void> {
    const empty = (fields ?? []).find((f) => !f.optional && !values[f.key]?.trim());
    if (empty) {
      error = t("install.needs", { name: plugin, field: empty.label });
      return;
    }
    busy = true;
    error = "";
    try {
      await client.mcp.updateFromRepository(plugin, values);
      onclose(true);
    } catch (e) {
      error = describe(e);
    } finally {
      busy = false;
    }
  }

  /** "t.me/BotFather" for a help link: the address without its scheme reads better. */
  function shortLink(url: string): string {
    return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
  }
</script>

<Modal
  title={t("pluginUpdates.update", { name: plugin })}
  description={t("pluginUpdates.valuesDescription")}
  width={560}
  onclose={() => onclose()}
>
  {#if fields === null && !error}
    <p class="text-meta">{t("common.loading")}</p>
  {:else if fields?.length}
    <div class="form">
      {#each fields as f (f.key)}
        <label class="field">
          <span class="field-label"
            >{f.label}{#if f.optional}<span class="text-caption"> · {t("pluginSettings.optional")}</span>{/if}</span
          >
          {#if f.secret}
            <SecretInput label={f.label} bind:value={values[f.key]} required={!f.optional} />
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
    {#if fields?.length}
      <button class="btn btn--primary" disabled={busy} onclick={update}
        >{busy ? t("pluginUpdates.busy") : t("pluginUpdates.updateNow")}</button
      >
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
  p {
    margin: 0;
  }
</style>
