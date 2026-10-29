<script lang="ts">
  import { resource } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";

  // In the status bar: the model the assistant answers with, the worker model in its tooltip. Loaded again when
  // settings change; hidden when it can't be loaded.
  const model = resource((c) => c.model.status(), ["settings"]);
</script>

{#if model.data && !model.error}
  <span class="model" title={t("chat.modelTip", { provider: model.data.provider, worker: model.data.worker_model })}
    >{model.data.model}</span
  >
{/if}

<style>
  .model {
    cursor: default;
    color: #e5b931;
  }
</style>
