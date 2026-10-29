<script lang="ts">
  import SecretInput from "../SecretInput.svelte";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
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

<SettingsCard id="web-search" title={t("webSearch.title")} sub={t("webSearch.sub")}>
  {#snippet status()}
    <span class="pill" class:pill--accent={s?.brave_key_set}>
      {s?.brave_key_set ? "Brave Search API" : t("webSearch.free")}
    </span>
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
  {:else if !s.brave_key_set}
    <ol class="steps">
      <li>
        {t("webSearch.open")} <a href="https://brave.com/search/api/" target="_blank" rel="noreferrer">brave.com/search/api</a>
        {t("webSearch.signUp")}
      </li>
      <li>{t("webSearch.dashboard")} <strong>API Keys</strong> {t("webSearch.copy")}</li>
      <li>{t("webSearch.paste")}</li>
    </ol>
    <form
      class="row"
      onsubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <SecretInput bind:value={key} placeholder={t("webSearch.apiKey")} label={t("webSearch.keyLabel")} />
      <button class="btn btn--primary" type="submit" disabled={saving}>{saving ? t("webSearch.checking") : t("common.save")}</button>
    </form>
  {:else}
    <p class="text-meta">{t("webSearch.usesBrave")}</p>
    <div class="row">
      <button class="btn btn--danger" onclick={() => act(() => client.webSearch.removeBraveKey())}>{t("webSearch.remove")}</button>
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
