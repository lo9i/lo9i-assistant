<script lang="ts">
  import { page } from "$app/state";
  import FileX from "@lucide/svelte/icons/file-x";
  import { resource } from "$lib/daemon.svelte";
  import { pageLabel, pageUrl } from "$lib/pages";
  import EmptyState from "$lib/ui/EmptyState.svelte";

  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const name = $derived(page.params.name ?? "");
  const server = $derived(servers.data?.find((s) => s.name === name && s.page));
</script>

<!-- Only the page: it has its own title and layout, so no top bar above it. -->
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
    height: 100dvh;
    max-width: 1600px;
    margin: 0 auto;
    padding: 16px;
  }
  iframe {
    width: 100%;
    height: 100%;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    /* Under the border too, the page's white would show through its translucent color. */
    background: var(--color-bg-page);
    background-clip: padding-box;
  }
</style>
