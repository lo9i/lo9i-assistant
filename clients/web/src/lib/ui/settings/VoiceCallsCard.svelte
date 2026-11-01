<script lang="ts">
  import SecretInput from "../SecretInput.svelte";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t, type Key } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  // Where the key calls use comes from (core/voice/key.py).
  const SOURCES: Record<string, Key> = {
    saved: "voiceCallsCard.usesSaved",
    model: "voiceCallsCard.usesModel",
    env: "voiceCallsCard.usesEnv",
  };

  const { client } = useDaemon();
  const loaded = resource((c) => c.voiceCalls.settings(), ["settings"]);
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
      await client.voiceCalls.setKey(key.trim());
      key = "";
    });
    saving = false;
  }
</script>

<SettingsCard id="voice-calls" title={t("voiceCallsCard.title")} sub={t("voiceCallsCard.sub")}>
  {#snippet status()}
    <span class="pill" class:pill--accent={!!s?.key_source} class:pill--warn={s !== undefined && !s.key_source}>
      {s?.key_source ? t("voiceCallsCard.ready") : t("voiceCallsCard.needsKey")}
    </span>
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
  {:else}
    {#if s.key_source}
      <p class="text-meta">{t(SOURCES[s.key_source])} {t("voiceCallsCard.howTo")}</p>
    {:else}
      <p class="text-meta">{t("voiceCallsCard.why")}</p>
    {/if}
    {#if s.key_source === "saved"}
      <div class="row">
        <button class="btn btn--danger" onclick={() => act(() => client.voiceCalls.removeKey())}>{t("voiceCallsCard.remove")}</button>
      </div>
    {:else}
      <ol class="steps">
        <li>
          {t("voiceCallsCard.open")}
          <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">platform.openai.com/api-keys</a>
          {t("voiceCallsCard.create")}
        </li>
        <li>{t("voiceCallsCard.paste")}</li>
      </ol>
      <form
        class="row"
        onsubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <SecretInput bind:value={key} placeholder="sk-…" label={t("voiceCallsCard.keyLabel")} />
        <button class="btn btn--primary" type="submit" disabled={saving}>{saving ? t("voiceCallsCard.checking") : t("common.save")}</button>
      </form>
    {/if}
    <dl>
      <dt class="micro-label">{t("voiceCallsCard.model")}</dt>
      <dd>{s.model}</dd>
    </dl>
    <p class="text-caption">{t("voiceCallsCard.cost")}</p>
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
  .text-meta,
  .text-caption {
    margin: 0;
  }
  dl {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 16px;
    margin: 0;
  }
  dd {
    margin: 0;
    font-family: var(--font-mono, monospace);
    font-size: var(--font-size-sm);
  }
</style>
