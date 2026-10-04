<script lang="ts">
  import SecretInput from "../SecretInput.svelte";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  const { client } = useDaemon();
  const loaded = resource((c) => c.webSearch.status(), ["integrations"]);
  const s = $derived(loaded.data);
  let key = $state("");
  let saving = $state(false);
  let error = $state("");

  async function act(action: () => Promise<unknown>): Promise<void> {
    try {
      await action();
      error = "";
    } catch (e) {
      error = describe(e);
    }
    loaded.reload();
  }

  async function save(): Promise<void> {
    if (!key.trim()) return;
    saving = true;
    await act(async () => {
      await client.webSearch.setBraveKey(key.trim());
      key = "";
    });
    saving = false;
  }
</script>

<SettingsCard
  id="web-search"
  title="Web search"
  sub="Public engines and free search services often block or limit automated searches. A Brave Search API key makes search reliable."
>
  {#snippet status()}
    <span class="pill" class:pill--accent={s?.brave_key_set}>
      {s?.brave_key_set ? "Brave Search API" : "Free services"}
    </span>
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else if !s.brave_key_set}
    <ol class="steps">
      <li>
        Open <a href="https://brave.com/search/api/" target="_blank" rel="noreferrer">brave.com/search/api</a> and sign up for the free plan.
      </li>
      <li>In the dashboard, open <strong>API Keys</strong> and copy the key.</li>
      <li>Paste it here. It's checked with one search, then kept encrypted on the assistant's computer.</li>
    </ol>
    <form
      class="row"
      onsubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <SecretInput bind:value={key} placeholder="API key" label="Brave Search API key" />
      <button class="btn btn--primary" type="submit" disabled={saving}>{saving ? "Checking…" : "Save"}</button>
    </form>
  {:else}
    <p class="text-meta">Searches use Brave. When Brave fails, they use public engines and free search services.</p>
    <div class="row">
      <button class="btn btn--danger" onclick={() => act(() => client.webSearch.removeBraveKey())}>Remove key</button>
    </div>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SettingsCard>

<style>
  .steps {
    margin: 0;
    padding-left: 20px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .text-meta {
    margin: 0;
  }
</style>
