<script lang="ts">
  import type { DispatchSetting } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  // A message written in the inbox goes on in the conversation it's about, or a new one; the worker model
  // picks (core/conversation/dispatch.py). Below the confidence it starts a new conversation, without asking.
  const { client } = useDaemon();
  const loaded = resource((c) => c.model.dispatch(), ["settings"]);
  const s = $derived(loaded.data);
  let error = $state("");

  async function save(setting: DispatchSetting): Promise<void> {
    try {
      await client.model.setDispatch(setting);
      error = "";
    } catch (e) {
      error = describe(e);
    }
    loaded.reload();
  }
</script>

<SettingsCard id="dispatch" title={t("dispatch.title")} sub={t("dispatch.sub")}>
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
  {:else}
    <label class="row">
      <span class="text-label">{t("dispatch.from")}</span>
      <input
        type="range"
        min="0.5"
        max="1"
        step="0.05"
        value={s.confidence}
        aria-label={t("dispatch.label")}
        onchange={(e) => save({ confidence: Number(e.currentTarget.value) })}
      />
      <span class="value">{Math.round(s.confidence * 100)}%</span>
    </label>
    <p class="text-meta">{t("dispatch.hint")}</p>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SettingsCard>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  input[type="range"] {
    flex: 1;
    min-width: 120px;
  }
  .value {
    min-width: 3ch;
    font-variant-numeric: tabular-nums;
  }
  .text-meta {
    margin: 0;
  }
</style>
