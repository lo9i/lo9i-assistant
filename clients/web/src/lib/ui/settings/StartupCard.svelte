<script lang="ts">
  import type { StartupStatus } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t, type Key } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";
  import Toggle from "../Toggle.svelte";

  const { client } = useDaemon();
  const loaded = resource((c) => c.system.startup(), []);
  let message = $state("");
  // The change asked for, until the daemon answers with the new status: the toggle shows it and takes no other tap
  // meanwhile, so a second tap during the macOS password dialog doesn't ask again.
  let changing = $state<boolean | null>(null);
  const s = $derived(loaded.data);

  const NOTES: Record<string, Key[]> = {
    macos: ["startup.macPassword", "startup.macSleep", "startup.macFileVault"],
    linux: ["startup.linuxService", "startup.linuxSleep", "startup.linuxOllama"],
  };
  const computer = $derived(s?.platform === "macos" ? t("startup.theMac") : t("startup.theComputer"));

  async function change(enable: boolean): Promise<void> {
    if (changing !== null) return;
    changing = enable;
    try {
      await ask(enable);
    } finally {
      changing = null;
    }
  }

  async function ask(enable: boolean): Promise<void> {
    message = s?.platform === "macos" ? t("startup.waitingPassword") : t("nav.working");
    try {
      const status = await (enable ? client.system.enableStartup() : client.system.disableStartup());
      loaded.data = status;
      message = done(enable, status);
    } catch (e) {
      message = describe(e);
      loaded.reload();
    }
  }

  /** An out-of-date start at boot installed as turning it on installs it now. */
  async function reinstall(): Promise<void> {
    if (changing !== null) return;
    changing = true;
    message = t("startup.waitingPassword");
    try {
      const status = await client.system.reinstallStartup();
      loaded.data = status;
      message = status.managed ? t("startup.reinstalledManaged") : t("startup.reinstalled");
    } catch (e) {
      message = describe(e);
      loaded.reload();
    } finally {
      changing = null;
    }
  }

  function done(enabled: boolean, s: StartupStatus): string {
    if (!enabled) return t("startup.turnedOff", { computer });
    const system = s.platform === "macos" ? "macOS" : "systemd";
    return s.managed ? t("startup.turnedOn") : t("startup.turnedOnRestarts", { system });
  }
</script>

<SettingsCard id="startup" title={t("startup.title")} sub={t("startup.sub", { computer })}>
  {#snippet status()}
    {#if s}
      {#if s.platform !== "unsupported"}
        <Toggle checked={changing ?? s.enabled} label={t("startup.title")} disabled={changing !== null} onchange={change} />
      {/if}
    {/if}
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
  {:else if s.platform === "unsupported"}
    <p class="text-meta">{t("startup.unsupported")}</p>
  {:else}
    <ul class="callout text-caption">
      {#each NOTES[s.platform] ?? [] as note (note)}<li>{t(note)}</li>{/each}
    </ul>
    {#if s.platform === "linux" && !s.starts_without_login}
      <p class="text-meta">
        <strong>{t("startup.lingering")}</strong>
        {t("startup.lingeringHint")} <code>sudo loginctl enable-linger $USER</code>
      </p>
    {/if}
    {#if s.enabled && s.includes_ollama}<p class="text-meta">{t("startup.ollama")}</p>{/if}
    {#if s.enabled && s.outdated?.length}
      <div class="outdated">
        <p class="text-meta"><strong>{t("startup.outdated")}</strong> {t("startup.outdatedHint")}</p>
        <ul class="text-caption">
          {#each s.outdated as why (why)}<li>{why}</li>{/each}
        </ul>
        <button class="btn btn--sm btn--primary" onclick={reinstall} disabled={changing !== null}>{t("startup.installAgain")}</button>
      </div>
    {/if}
    {#if message}<p class="text-meta">{message}</p>{/if}
  {/if}
</SettingsCard>

<style>
  .callout {
    margin: 0;
    padding: 16px 16px 16px 32px;
    border-radius: var(--radius-sm);
    border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
    background: color-mix(in srgb, var(--color-text-primary) 4%, transparent);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  p {
    margin: 0;
  }
  .outdated {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  .outdated ul {
    margin: 0;
    padding-left: 20px;
  }
</style>
