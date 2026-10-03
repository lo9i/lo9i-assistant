<script lang="ts">
  import type { ModelChange, ModelProvider } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  const { client } = useDaemon();
  const loaded = resource((c) => c.model.status(), ["settings"]);
  const providers = resource((c) => c.model.providers(), []);
  const s = $derived(loaded.data);
  let form = $state<ModelChange>({ provider: "", api_key: "", base_url: "", model: "", worker_model: "" });
  let message = $state("");
  let testing = $state(false);
  const provider = $derived<ModelProvider | undefined>(providers.data?.find((p) => p.id === form.provider));
  // The saved key stays when the provider doesn't change.
  const keepsKey = $derived(s !== undefined && s.key_set && form.provider === s.provider);

  // The form starts from what's in use, and follows it when it changes elsewhere.
  $effect(() => {
    if (s) form = { provider: s.provider, api_key: "", base_url: s.base_url, model: s.model, worker_model: s.worker_model };
  });

  /** A provider's suggested models, or the ones in use when it's the current provider. */
  function choose(id: string): void {
    const p = providers.data?.find((x) => x.id === id);
    const current = s !== undefined && id === s.provider;
    form = {
      provider: id,
      api_key: "",
      base_url: current ? (s?.base_url ?? "") : "",
      model: current ? (s?.model ?? "") : (p?.model ?? ""),
      worker_model: current ? (s?.worker_model ?? "") : (p?.worker_model ?? ""),
    };
  }

  async function save(): Promise<void> {
    testing = true;
    message = "Testing the models…";
    try {
      await client.model.set({ ...form, base_url: provider?.takes_base_url ? form.base_url : "" });
      message = "Saved ✓ Both models answered. New messages use them.";
    } catch (e) {
      message = describe(e);
    } finally {
      testing = false;
    }
    loaded.reload();
  }

  async function useEnv(): Promise<void> {
    try {
      await client.model.reset();
      message = "Using the model from .env.";
    } catch (e) {
      message = describe(e);
    }
    loaded.reload();
  }

  function providerName(id: string): string {
    return providers.data?.find((p) => p.id === id)?.name ?? id;
  }
</script>

<SettingsCard id="model" title="Model" sub="Which AI model the assistant uses. Set here, it overrides .env.">
  {#snippet status()}
    {#if s}
      <span class="pill" class:pill--accent={s.source === "app"}>{providerName(s.provider)} · {s.source === "app" ? "set here" : "from .env"}</span>
    {/if}
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else}
    <form
      class="fields"
      onsubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <label class="fields">
        <span class="text-label">Provider</span>
        <select class="input" value={form.provider} aria-label="Provider" onchange={(e) => choose(e.currentTarget.value)}>
          {#each providers.data ?? [] as p (p.id)}
            <option value={p.id}>{p.name}</option>
          {/each}
        </select>
      </label>
      {#if provider}
        <label class="fields">
          <span class="text-label">{provider.key_label}</span>
          <input
            class="input"
            type="password"
            autocomplete="off"
            placeholder={keepsKey ? "Saved — leave empty to keep it" : provider.key_label}
            aria-label={provider.key_label}
            bind:value={form.api_key}
          />
          <span class="text-caption">{provider.key_help}</span>
        </label>
        {#if provider.takes_base_url}
          <label class="fields">
            <span class="text-label">Server URL</span>
            <input class="input" placeholder="Empty for OpenAI; Ollama: http://localhost:11434/v1" aria-label="Server URL" bind:value={form.base_url} />
          </label>
        {/if}
      {/if}
      <div class="row">
        <label class="fields grow">
          <span class="text-label">Main model</span>
          <input class="input" aria-label="Main model" bind:value={form.model} />
        </label>
        <label class="fields grow">
          <span class="text-label">Worker model (summaries, titles)</span>
          <input class="input" aria-label="Worker model" bind:value={form.worker_model} />
        </label>
      </div>
      <div class="row">
        <button class="btn btn--primary" type="submit" disabled={testing}>Save and test</button>
        {#if s.source === "app"}
          <button class="btn btn--neutral" type="button" disabled={testing} onclick={useEnv}>Use .env instead</button>
        {/if}
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
