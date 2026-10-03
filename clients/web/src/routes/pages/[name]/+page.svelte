<script lang="ts">
  import { page } from "$app/state";
  import FileX from "@lucide/svelte/icons/file-x";
  import { resource } from "$lib/daemon.svelte";
  import { pageLabel, pageUrl } from "$lib/pages";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const name = $derived(page.params.name ?? "");
  const server = $derived(servers.data?.find((s) => s.name === name && s.page));
</script>

<TopBar title={pageLabel(name)} />

<div class="frame-shell">
  {#if servers.data === undefined}
    <p class="text-meta">{servers.error ?? "Loading…"}</p>
  {:else if !server}
    <EmptyState icon={FileX} title="No page" text="No MCP server called {name} with a page is installed." />
  {:else if !server.enabled}
    <EmptyState icon={FileX} title="Turned off" text="Turn {name} on in MCP servers to see its page." />
  {:else}
    <!-- The page's own origin (daemon/pages.py): it can't reach the web app or its API. -->
    <iframe title={pageLabel(name)} src={pageUrl(name, window.location)}></iframe>
  {/if}
</div>

<style>
  .frame-shell {
    height: calc(100dvh - 76px);
    max-width: 1600px;
    margin: 0 auto;
    padding: 0 16px 16px;
  }
  iframe {
    width: 100%;
    height: 100%;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-surface, white);
  }
</style>
