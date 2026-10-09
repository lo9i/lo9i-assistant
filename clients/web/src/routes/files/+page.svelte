<script lang="ts">
  import { resolve } from "$app/paths";
  import type { UploadedFile } from "$lib/api/types";
  import FileIcon from "@lucide/svelte/icons/file";
  import Files from "@lucide/svelte/icons/files";
  import { resource } from "$lib/daemon.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import FilePreview from "$lib/ui/FilePreview.svelte";
  import SearchField from "$lib/ui/SearchField.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  // A file arrives with a message, which updates its conversation; deleting one removes its files.
  const files = resource((c) => c.files.list(), ["conversations"]);
  let picked = $state<string | null>(null);
  let query = $state("");
  // By name, type, where it came from or conversation.
  const shown = $derived(
    (files.data ?? []).filter((f) =>
      `${f.name} ${f.media_type} ${source(f)} ${f.conversation}`.toLowerCase().includes(query.trim().toLowerCase()),
    ),
  );
  // Until one is picked: the newest.
  const file = $derived(files.data?.find((f) => f.path === picked) ?? files.data?.[0]);

  // The user, or the tool whose result brought it (an MCP tool as "server: tool").
  function source(f: UploadedFile): string {
    const [, server, tool] = f.tool.match(/^mcp__(.+?)__(.+)$/) ?? [];
    return server ? `${server}: ${tool}` : f.tool || "You";
  }

  function when(iso: string): string {
    return new Date(iso).toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function size(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
</script>

<TopBar title="Files" />

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Conversation files</h2>
        <p class="text-meta">
          Files you sent and files tools brought (email attachments, images), newest first. Click one to see or download it on the right.
        </p>
      </div>
      <div class="tools">
        <SearchField bind:value={query} label="Search files" />
        {#if files.data}<span class="pill">{files.data.length}</span>{/if}
      </div>
    </header>
    <div class="scroll">
      {#if files.error}
        <p class="error-text pad">{files.error}</p>
      {:else if files.data?.length === 0}
        <EmptyState icon={Files} title="No files yet" text="Files you attach to a message, and the ones tools bring in, show up here." />
      {:else if files.data && file}
        <table class="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th class="hide-narrow">Type</th>
              <th>Size</th>
              <th class="hide-narrow">From</th>
              <th class="hide-narrow">Conversation</th>
              <th>Added</th>
            </tr>
          </thead>
          <tbody>
            {#each shown as f (f.path)}
              <tr class:selected={f.path === file.path} onclick={() => (picked = f.path)}>
                <td><button class="row-button" onclick={() => (picked = f.path)}>{f.name}</button></td>
                <td class="text-label hide-narrow">{f.media_type}</td>
                <td class="text-label">{size(f.size)}</td>
                <td class="text-label hide-narrow">{source(f)}</td>
                <td class="text-label hide-narrow">{f.conversation || "Untitled"}</td>
                <td class="text-label">{when(f.uploaded_at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
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
          <dt class="micro-label">Type</dt>
          <dd>{file.media_type}</dd>
          <dt class="micro-label">Size</dt>
          <dd>{size(file.size)}</dd>
          <dt class="micro-label">From</dt>
          <dd>{source(file)}</dd>
          <dt class="micro-label">Added</dt>
          <dd>{when(file.uploaded_at)}</dd>
          <dt class="micro-label">Conversation</dt>
          <dd><a href="{resolve('/conversations')}?c={file.thread_id}">{file.conversation || "Untitled"}</a></dd>
        </dl>
        <FilePreview {file} />
      </section>
    {:else}
      <section class="details surface--glass">
        <EmptyState icon={FileIcon} title="No file selected" text="Pick one from the table." />
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
    padding: 0 16px 16px;
    height: calc(100dvh - 76px);
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
