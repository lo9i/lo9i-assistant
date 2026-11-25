<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";
  import Toggle from "../Toggle.svelte";

  // The assistant's bash commands in a container that sees only the workspace (core/sandbox/). Kept by the daemon, so
  // it holds for every device; off until the user turns it on, and it can't be without Docker or Podman running.
  const { client } = useDaemon();
  const loaded = resource((c) => c.sandbox.status(), ["settings"]);
  const s = $derived(loaded.data);
  const runtime = $derived(s?.runtime === "podman" ? "Podman" : "Docker");
  let turning = $state(false);
  let error = $state("");

  async function change(enabled: boolean): Promise<void> {
    turning = enabled;
    try {
      await client.sandbox.setEnabled(enabled);
      error = "";
    } catch (e) {
      error = describe(e);
    }
    turning = false;
    loaded.reload();
  }
</script>

<SettingsCard id="sandbox" title={t("sandboxCard.title")} sub={t("sandboxCard.sub")}>
  {#snippet status()}
    {#if s}
      <span class="pill" class:pill--accent={s.enabled} class:pill--danger={s.enabled && !s.available}>
        {s.enabled ? t("sandboxCard.on") : s.available ? t("sandboxCard.off") : t("sandboxCard.noRuntime")}
      </span>
    {/if}
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
  {:else}
    <div class="switch">
      <span class="text-label">{t("sandboxCard.run")}</span>
      <Toggle checked={s.enabled} disabled={turning || (!s.enabled && !s.available)} label={t("sandboxCard.runLabel")} onchange={change} />
    </div>
    {#if turning}
      <p class="text-meta">{t("sandboxCard.starting")}</p>
    {:else if s.problem}
      <p class={s.enabled ? "error-text" : "text-meta"}>{s.problem} {s.fix}</p>
    {:else if s.enabled}
      <p class="text-meta">{t("sandboxCard.uses", { runtime, image: s.image })}</p>
    {:else}
      <p class="text-meta">{t("sandboxCard.available", { runtime })}</p>
    {/if}
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SettingsCard>

<style>
  .switch {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .text-meta,
  .error-text {
    margin: 0;
  }
</style>
