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
  /* The page fills the space beside the sidebar and lays itself out, like the app's own pages. */
  .frame-shell {
    height: 100dvh;
    padding-top: 16px;
    box-sizing: border-box;
  }
  .frame-shell > :global(:not(iframe)) {
    max-width: 1600px;
    margin: 0 auto;
    padding: 16px;
  }
  /* No border and no background: a page that leaves its own background out shows the app's through it,
     so it reads as part of the app rather than a page set into it. */
  iframe {
    display: block;
    width: 100%;
    height: 100%;
    border: 0;
    background: transparent;
  }
</style>
