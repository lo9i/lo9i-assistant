<script lang="ts">
  import { untrack } from "svelte";
  import type { ModelChange, ModelOption, ModelProvider } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";
  import SecretInput from "../SecretInput.svelte";

  const { client } = useDaemon();
  const loaded = resource((c) => c.model.status(), ["settings"]);
  const providers = resource((c) => c.model.providers(), ["settings"]);
  const s = $derived(loaded.data);
  let form = $state<ModelChange>({ provider: "", values: {}, model: "", worker_model: "" });
  let message = $state("");
  let testing = $state(false);
  const provider = $derived<ModelProvider | undefined>(providers.data?.find((p) => p.id === form.provider));
  const current = $derived(s !== undefined && form.provider === s.provider);
  // The provider's models for the key typed or saved, to pick from (Copilot lists them); empty
  // otherwise, and the model ids are typed.
  let options = $state<ModelOption[]>([]);
  // Sorted by name; a model in use that the provider no longer lists stays offered, so it shows.
  function choices(current: string): ModelOption[] {
    const known =
      options.some((m) => m.id === current) || !current ? [] : [{ id: current, name: t("model.notListed", { model: current }) }];
    return [...options, ...known].sort((a, b) => a.name.localeCompare(b.name));
  }
  let listing = $state("");

  // The form starts from what's in use, and follows it when it changes elsewhere.
  $effect(() => {
    if (s) form = { provider: s.provider, values: { ...s.values }, model: s.model, worker_model: s.worker_model };
  });

  /** A provider's suggested models, or the ones in use when it's the current provider. */
  function choose(id: string): void {
    const p = providers.data?.find((x) => x.id === id);
    const inUse = s !== undefined && id === s.provider;
    form = {
      provider: id,
      values: inUse ? { ...(s?.values ?? {}) } : {},
      model: inUse ? (s?.model ?? "") : (p?.model ?? ""),
      worker_model: inUse ? (s?.worker_model ?? "") : (p?.worker_model ?? ""),
    };
  }

  async function loadModels(): Promise<void> {
    if (!form.provider) return;
    try {
      options = await client.model.available(form.provider, form.values);
      listing = "";
    } catch (e) {
      options = [];
      listing = describe(e);
    }
  }

  // Again whenever the provider changes; after a key is typed, when it's left (SecretInput's onchange).
  $effect(() => {
    void form.provider;
    untrack(loadModels);
  });

  /** Saved secrets are never sent back: an empty field keeps them. */
  function placeholder(key: string, label: string, required: boolean): string {
    if (current && s?.secrets_set.includes(key)) return t("model.savedSecret");
    return required ? label : t("model.optional", { label });
  }

  async function save(): Promise<void> {
    testing = true;
    message = provider && !provider.installed ? t("model.installing", { package: provider.package }) : t("model.testing");
    try {
      await client.model.set(form);
      message = t("model.saved");
      providers.reload();
    } catch (e) {
      message = describe(e);
    } finally {
      testing = false;
    }
    loaded.reload();
  }

  function providerName(id: string): string {
    return providers.data?.find((p) => p.id === id)?.name ?? id;
  }
</script>

<!-- A dropdown of the provider's models when it lists them, else the model id typed. -->
{#snippet modelField(label: string, key: "model" | "worker_model")}
  {#if options.length}
    <select class="input" aria-label={label} bind:value={form[key]}>
      {#each choices(form[key]) as m (m.id)}<option value={m.id}>{m.name}</option>{/each}
    </select>
  {:else}
    <input class="input" aria-label={label} bind:value={form[key]} />
  {/if}
{/snippet}

<SettingsCard id="model" title={t("model.title")} sub={t("model.sub")}>
  {#snippet status()}
    {#if s}
      <span class="pill" class:pill--accent={s.source === "app"}
        >{providerName(s.provider)} · {s.source === "app" ? t("model.setHere") : t("model.fromEnv")}</span
      >
    {/if}
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
  {:else}
    <form
      class="fields"
      onsubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <label class="fields">
        <span class="text-label">{t("model.provider")}</span>
        <select class="input" value={form.provider} aria-label={t("model.provider")} onchange={(e) => choose(e.currentTarget.value)}>
          {#each providers.data ?? [] as p (p.id)}
            <option value={p.id}>{p.name}</option>
          {/each}
        </select>
      </label>
      {#if provider}
        {#if provider.help}<span class="text-caption">{provider.help}</span>{/if}
        {#each provider.fields as f (f.key)}
          <label class="fields">
            <span class="text-label">{f.label}</span>
            {#if f.options?.length}
              <select
                class="input"
                aria-label={f.label}
                bind:value={() => form.values[f.key] || f.options[0], (v) => (form.values[f.key] = v)}
              >
                {#each f.options as o (o)}<option value={o}>{o}</option>{/each}
              </select>
            {:else if f.secret}
              <SecretInput
                label={f.label}
                placeholder={placeholder(f.key, f.label, f.required)}
                bind:value={form.values[f.key]}
                onchange={loadModels}
              />
            {:else}
              <input
                class="input"
                autocomplete="off"
                placeholder={placeholder(f.key, f.label, f.required)}
                aria-label={f.label}
                bind:value={form.values[f.key]}
              />
            {/if}
            {#if f.help}<span class="text-caption">{f.help}</span>{/if}
          </label>
        {/each}
        {#if !provider.installed}
          <span class="text-caption">{t("model.installsBefore")} <code>{provider.package}</code> {t("model.installsAfter")}</span>
        {/if}
      {/if}
      <div class="row">
        <label class="fields grow">
          <span class="text-label">{t("model.main")}</span>
          {@render modelField(t("model.main"), "model")}
        </label>
        <label class="fields grow">
          <span class="text-label">{t("model.workerHint")}</span>
          {@render modelField(t("model.worker"), "worker_model")}
        </label>
      </div>
      {#if options.length}
        <span class="text-caption">{t("model.available", { count: options.length })}</span>
      {:else if listing}
        <span class="text-caption">{t("model.listFailed", { error: listing })}</span>
      {/if}
      <div class="row">
        <button class="btn btn--primary" type="submit" disabled={testing}>{t("model.saveAndTest")}</button>
      </div>
    </form>
  {/if}
  {#if message}<p class="text-meta">{message}</p>{/if}
</SettingsCard>

<style>
  .fields {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .grow {
    flex: 1;
    min-width: 200px;
  }
  p {
    margin: 0;
  }
</style>
