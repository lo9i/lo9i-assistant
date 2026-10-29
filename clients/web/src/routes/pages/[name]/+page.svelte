<script lang="ts">
  import { untrack } from "svelte";
  import { page } from "$app/state";
  import FileX from "@lucide/svelte/icons/file-x";
  import { resource } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { pageLabel, pagesOrigin, pageUrl, themeMessage } from "$lib/pages";
  import { theme } from "$lib/theme.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";

  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const name = $derived(page.params.name ?? "");
  // Where on the page to open it: a Home item's place (`?path=titles/12`).
  const path = $derived(page.url.searchParams.get("path") ?? "");
  const server = $derived(servers.data?.find((s) => s.name === name && s.page));
  // The page is told the app's theme in its address once; a change after goes to it as a message, so the
  // frame isn't loaded again.
  const src = $derived(
    pageUrl(
      name,
      window.location,
      untrack(() => theme.resolved),
      path,
    ),
  );
  let frame = $state<HTMLIFrameElement | null>(null);

  $effect(() => {
    frame?.contentWindow?.postMessage(themeMessage(theme.resolved), pagesOrigin(window.location));
  });
</script>

<!-- Only the page: it has its own title and layout, so no top bar above it. -->
<div class="frame-shell">
  {#if servers.data === undefined}
    <p class="text-meta">{servers.error ?? t("common.loading")}</p>
  {:else if !server}
    <EmptyState icon={FileX} title={t("pagesPage.none")} text={t("pagesPage.noneHint", { name })} />
  {:else if !server.enabled}
    <EmptyState icon={FileX} title={t("pagesPage.off")} text={t("pagesPage.offHint", { name })} />
  {:else}
    <!-- The page's own origin (daemon/pages.py): it can't reach the web app or its API. -->
    <iframe bind:this={frame} title={pageLabel(name)} {src}></iframe>
  {/if}
</div>

<style>
  /* The page fills the space beside the sidebar and lays itself out, like the app's own pages. */
  .frame-shell {
    height: 100dvh;
    padding-top: 8px;
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
