<script lang="ts">
  import { resolve } from "$app/paths";
  import { resource } from "$lib/daemon.svelte";
  import { t, type Key } from "$lib/i18n.svelte";

  // The settings tabs. About you, Plugins, MCP servers, Skills, Logs and Health are pages of their own shown as tabs.
  let { active }: { active: string } = $props();
  // Installed plugins with a newer version in the extras, as on the sidebar.
  const updates = resource((c) => c.repositories.updates(), ["plugins", "mcp", "skills", "settings"]);
  const TABS: { id: string; label: Key; href: string }[] = [
    { id: "general", label: "settings.tabs.general", href: `${resolve("/settings")}?tab=general` },
    { id: "memory", label: "settings.tabs.memory", href: resolve("/memory") },
    { id: "model", label: "settings.tabs.model", href: `${resolve("/settings")}?tab=model` },
    { id: "prompt", label: "settings.tabs.prompt", href: `${resolve("/settings")}?tab=prompt` },
    { id: "audio", label: "settings.tabs.audio", href: `${resolve("/settings")}?tab=audio` },
    { id: "plugins", label: "settings.tabs.plugins", href: resolve("/plugins") },
    { id: "mcp", label: "settings.tabs.mcp", href: resolve("/mcp") },
    { id: "skills", label: "settings.tabs.skills", href: resolve("/skills") },
    { id: "system", label: "settings.tabs.system", href: `${resolve("/settings")}?tab=system` },
    { id: "logs", label: "settings.tabs.logs", href: resolve("/logs") },
    { id: "doctor", label: "settings.tabs.doctor", href: resolve("/doctor") },
  ];
</script>

<nav class="tabs" aria-label={t("nav.settings")}>
  {#each TABS as tab (tab.id)}
    <a href={tab.href} class:active={tab.id === active} aria-current={tab.id === active ? "page" : undefined}>
      {t(tab.label)}
      {#if tab.id === "plugins" && updates.data?.length}<span
          class="count"
          aria-label={t("settings.updatesCount", { count: updates.data.length })}>{updates.data.length}</span
        >{/if}
    </a>
  {/each}
</nav>

<style>
  .count {
    margin-left: 4px;
    padding: 0 6px;
    border-radius: var(--radius-full);
    background: var(--color-action-primary);
    color: var(--color-action-on-primary);
    font-size: var(--font-size-xs);
  }
</style>
