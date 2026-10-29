<script lang="ts">
  import { resolve } from "$app/paths";
  import type { UploadedFile } from "$lib/api/types";
  import FileIcon from "@lucide/svelte/icons/file";
  import Files from "@lucide/svelte/icons/files";
  import { pagedResource } from "$lib/daemon.svelte";
  import { formatDate, formatNumber, t } from "$lib/i18n.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import FilePreview from "$lib/ui/FilePreview.svelte";
  import ListEnd from "$lib/ui/ListEnd.svelte";
  import SearchField from "$lib/ui/SearchField.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  let query = $state("");
  // The daemon searches by name, type, where it came from or conversation, once typing pauses.
  let searched = $state("");
  $effect(() => {
    const words = query.trim();
    const timer = setTimeout(() => (searched = words), 250);
    return () => clearTimeout(timer);
  });
  // A page at a time as the table is scrolled. A file arrives with a message, which updates its conversation;
  // deleting one removes its files.
  const files = pagedResource(
    (c, page) => c.files.list(searched, page),
    (f) => f.path,
    ["conversations"],
  );
  let picked = $state<UploadedFile | null>(null);
  // Until one is picked: the newest. A search that leaves the picked one out keeps showing it.
  const file = $derived(files.items.find((f) => f.path === picked?.path) ?? (searched ? picked : null) ?? files.items[0]);

  // The user, or the tool whose result brought it (an MCP tool as "server: tool").
  function source(f: UploadedFile): string {
    const [, server, tool] = f.tool.match(/^mcp__(.+?)__(.+)$/) ?? [];
    return server ? `${server}: ${tool}` : f.tool || t("files.you");
  }

  function when(iso: string): string {
    return formatDate(iso, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function size(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    const one = (n: number) => formatNumber(n, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    if (bytes < 1024 * 1024) return `${one(bytes / 1024)} KB`;
    return `${one(bytes / (1024 * 1024))} MB`;
  }
</script>

<TopBar title={t("nav.files")} />

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">{t("files.title")}</h2>
        <p class="text-meta">{t("files.hint")}</p>
      </div>
      <div class="tools">
        <SearchField bind:value={query} label={t("files.search")} />
        {#if files.loaded}<span class="pill">{files.items.length}{files.done ? "" : "+"}</span>{/if}
      </div>
    </header>
    <div class="scroll">
      {#if files.error && !files.items.length}
        <p class="error-text pad">{files.error}</p>
      {:else if files.loaded && !files.items.length}
        {#if searched}
          <p class="text-meta pad">{t("files.noMatch", { query: searched })}</p>
        {:else}
          <EmptyState icon={Files} title={t("files.none")} text={t("files.noneHint")} />
        {/if}
      {:else if file}
        <table class="data-table">
          <thead>
            <tr>
              <th>{t("alerts.name")}</th>
              <th class="hide-narrow">{t("files.type")}</th>
              <th>{t("files.size")}</th>
              <th class="hide-narrow">{t("devices.from")}</th>
              <th class="hide-narrow">{t("tokens.conversation")}</th>
              <th>{t("files.added")}</th>
            </tr>
          </thead>
          <tbody>
            {#each files.items as f (f.path)}
              <tr class:selected={f.path === file.path} onclick={() => (picked = f)}>
                <td><button class="row-button" onclick={() => (picked = f)}>{f.name}</button></td>
                <td class="text-label hide-narrow">{f.media_type}</td>
                <td class="text-label">{size(f.size)}</td>
                <td class="text-label hide-narrow">{source(f)}</td>
                <td class="text-label hide-narrow">{f.conversation || t("common.untitled")}</td>
                <td class="text-label">{when(f.uploaded_at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        <ListEnd list={files} />
      {/if}
    </div>
  </section>

  <div class="column">
    {#if file}
      <section class="details surface--glass">
        <header>
          <h2 class="text-heading">{file.name}</h2>
        </header>
        <dl>
          <dt class="micro-label">{t("files.type")}</dt>
          <dd>{file.media_type}</dd>
          <dt class="micro-label">{t("files.size")}</dt>
          <dd>{size(file.size)}</dd>
          <dt class="micro-label">{t("devices.from")}</dt>
          <dd>{source(file)}</dd>
          <dt class="micro-label">{t("files.added")}</dt>
          <dd>{when(file.uploaded_at)}</dd>
          <dt class="micro-label">{t("tokens.conversation")}</dt>
          <dd><a href="{resolve('/conversations')}?c={file.thread_id}">{file.conversation || t("common.untitled")}</a></dd>
        </dl>
        <FilePreview {file} />
      </section>
    {:else}
      <section class="details surface--glass">
        <EmptyState icon={FileIcon} title={t("files.noneSelected")} text={t("files.pickOne")} />
      </section>
    {/if}
  </div>
</div>

<style>
  .screen {
    display: flex;
    /* Cards take the height of their content, up to the screen; long lists scroll inside. */
    align-items: flex-start;
    gap: 16px;
    padding: 0 16px 8px;
    height: calc(100dvh - var(--top-bar-height));
    max-width: 1600px;
    margin: 0 auto;
  }
  /* The table takes three quarters of the width, the file the rest. */
  .table-card {
    flex: 3 1 0;
    min-width: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .column {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 16px 24px;
    min-height: 66px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .tools {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .scroll {
    overflow-y: auto;
    min-height: 0;
  }
  .data-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .pad {
    padding: 24px;
  }
  tr {
    cursor: pointer;
  }
  tr.selected {
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
  }
  tr.selected td:first-child {
    box-shadow: inset 3px 0 0 var(--color-accent);
  }
  .row-button {
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    cursor: pointer;
  }
  .details {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
  }
  .details header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    margin: 0;
    align-items: baseline;
  }
  dd {
    margin: 0;
    text-align: right;
  }
  /* Stacked, the page scrolls: each part takes its own height instead of a share of the screen. */
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
      align-items: stretch;
      height: auto;
    }
    .table-card,
    .column {
      flex: none;
    }
  }
</style>
