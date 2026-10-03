<script lang="ts">
  import { resolve } from "$app/paths";
  import { resource } from "$lib/daemon.svelte";

  // The settings tabs. About you, Skills, Plugins and MCP servers are pages of their own (lists with details) shown as tabs.
  let { active }: { active: string } = $props();
  // Installed plugins with a newer version in the extras, as on the sidebar.
  const updates = resource((c) => c.repositories.updates(), ["plugins", "mcp", "skills", "settings"]);
  const TABS = [
    { id: "general", label: "General", href: `${resolve("/settings")}?tab=general` },
    { id: "integrations", label: "Integrations", href: `${resolve("/settings")}?tab=integrations` },
    { id: "audio", label: "Audio", href: `${resolve("/settings")}?tab=audio` },
    { id: "memory", label: "About you", href: resolve("/memory") },
    { id: "skills", label: "Skills", href: resolve("/skills") },
    { id: "plugins", label: "Plugins", href: resolve("/plugins") },
    { id: "mcp", label: "MCP servers", href: resolve("/mcp") },
  ];
</script>

<nav class="tabs" aria-label="Settings">
  {#each TABS as t (t.id)}
    <a href={t.href} class:active={t.id === active} aria-current={t.id === active ? "page" : undefined}>
      {t.label}
      {#if t.id === "plugins" && updates.data?.length}<span class="count" aria-label="{updates.data.length} updates">{updates.data.length}</span>{/if}
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
