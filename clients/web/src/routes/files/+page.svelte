<script lang="ts">
  import { resolve } from "$app/paths";
  import type { UploadedFile } from "$lib/api/types";
  import FileIcon from "@lucide/svelte/icons/file";
  import Files from "@lucide/svelte/icons/files";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { pageWithFiles, stillShown, ticked, tickedAll } from "$lib/fileSelection";
  import { formatDate, formatNumber, t } from "$lib/i18n.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import FilePreview from "$lib/ui/FilePreview.svelte";
  import Pager from "$lib/ui/Pager.svelte";
  import SearchField from "$lib/ui/SearchField.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const PAGE_SIZE = 50;
  const { client, notices } = useDaemon();

  let query = $state("");
  // The daemon searches by name, type, where it came from or conversation, once typing pauses. A new search starts
  // at the first page.
  let searched = $state("");
  let page = $state(0);
  $effect(() => {
    const words = query.trim();
    const timer = setTimeout(() => {
      if (words === searched) return;
      searched = words;
      page = 0;
    }, 250);
    return () => clearTimeout(timer);
  });
  // A page of them and how many match, to page through. A file arrives with a message, which updates its
  // conversation; deleting one removes its files, and files deleted here say so too.
  const listing = resource(
    async (c) => {
      const [files, total] = await Promise.all([
        c.files.list(searched, { offset: page * PAGE_SIZE, limit: PAGE_SIZE }),
        c.files.count(searched),
      ]);
      return { files, total };
    },
    ["conversations", "files"],
  );
  const shown = $derived(listing.data?.files ?? []);
  const total = $derived(listing.data?.total ?? 0);
  // A page left empty (its last files deleted, here or elsewhere) gives way to the last one there is.
  $effect(() => {
    if (listing.data && !listing.data.files.length && page > 0) page = pageWithFiles(page, listing.data.total, PAGE_SIZE);
  });

  let picked = $state<UploadedFile | null>(null);
  // Until one is picked: the newest. A search that leaves the picked one out keeps showing it.
  const file = $derived(shown.find((f) => f.path === picked?.path) ?? (searched ? picked : null) ?? shown[0]);

  // The files ticked to delete together, on the page shown only.
  let picks = $state<string[]>([]);
  const paths = $derived(shown.map((f) => f.path));
  const chosen = $derived(stillShown(picks, paths));
  const allChosen = $derived(paths.length > 0 && chosen.length === paths.length);
  // The files asked to delete, until the user answers in the bar above the table; the page stays usable meanwhile.
  let confirming = $state<string[] | null>(null);
  let deleting = $state(false);
  $effect(() => {
    void [page, searched];
    picks = [];
    confirming = null;
  });

  function tick(path: string, on: boolean): void {
    picks = ticked(picks, path, on);
    confirming = null;
  }

  function tickPage(on: boolean): void {
    picks = tickedAll(picks, paths, on);
    confirming = null;
  }

  function question(asked: string[]): string {
    const one = asked.length === 1 ? shown.find((f) => f.path === asked[0]) : undefined;
    return one ? t("files.deleteQuestionOne", { name: one.name }) : t("files.deleteQuestion", { count: asked.length });
  }

  async function deleteConfirmed(asked: string[]): Promise<void> {
    deleting = true;
    try {
      const deleted = await client.files.delete(asked);
      picks = picks.filter((p) => !deleted.includes(p));
      if (picked && deleted.includes(picked.path)) picked = null;
      notices.notify(t("files.deleted", { count: deleted.length }));
      listing.reload();
    } catch (e) {
      notices.report(e);
    } finally {
      deleting = false;
      confirming = null;
    }
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === "Escape" && confirming && !deleting) confirming = null;
  }

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

<svelte:window onkeydown={onKey} />

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
        {#if listing.data}<span class="pill">{total}</span>{/if}
      </div>
    </header>
    {#if confirming}
      {@const asked = confirming}
      <div class="action-bar confirming" role="status">
        <div>
          <strong class="text-label">{question(asked)}</strong>
          <p class="text-meta">{t("files.deleteText")}</p>
        </div>
        <div class="actions">
          <button class="btn btn--ghost btn--sm" disabled={deleting} onclick={() => (confirming = null)}>{t("common.cancel")}</button>
          <button class="btn btn--danger btn--sm" disabled={deleting} onclick={() => deleteConfirmed(asked)}>
            <Trash2 size={14} />
            {deleting ? t("files.deleting") : t("common.delete")}
          </button>
        </div>
      </div>
    {:else if chosen.length}
      <div class="action-bar" role="status">
        <span class="text-label">{t("files.selected", { count: chosen.length })}</span>
        <div class="actions">
          <button class="btn btn--ghost btn--sm" onclick={() => (picks = [])}>{t("files.clearSelection")}</button>
          <button class="btn btn--danger btn--sm" onclick={() => (confirming = chosen)}
            ><Trash2 size={14} /> {t("files.deleteSelected")}</button
          >
        </div>
      </div>
    {/if}
    <div class="scroll">
      {#if listing.error && !listing.data}
        <p class="error-text pad">{listing.error}</p>
      {:else if listing.data && !shown.length && page === 0}
        {#if searched}
          <p class="text-meta pad">{t("files.noMatch", { query: searched })}</p>
        {:else}
          <EmptyState icon={Files} title={t("files.none")} text={t("files.noneHint")} />
        {/if}
      {:else if file}
        <table class="data-table">
          <thead>
            <tr>
              <th class="check">
                <input
                  type="checkbox"
                  aria-label={t("files.selectPage")}
                  title={t("files.selectPage")}
                  checked={allChosen}
                  {@attach (box) => {
                    box.indeterminate = chosen.length > 0 && !allChosen;
                  }}
                  onchange={(e) => tickPage(e.currentTarget.checked)}
                />
              </th>
              <th>{t("alerts.name")}</th>
              <th class="hide-narrow">{t("files.type")}</th>
              <th>{t("files.size")}</th>
              <th class="hide-narrow">{t("devices.from")}</th>
              <th class="hide-narrow">{t("tokens.conversation")}</th>
              <th>{t("files.added")}</th>
              <th class="row-actions" aria-label={t("files.actions")}></th>
            </tr>
          </thead>
          <tbody>
            {#each shown as f (f.path)}
              <tr class:selected={f.path === file.path} class:ticked={chosen.includes(f.path)} onclick={() => (picked = f)}>
                <td class="check">
                  <input
                    type="checkbox"
                    aria-label={t("files.select", { name: f.name })}
                    checked={chosen.includes(f.path)}
                    onclick={(e) => e.stopPropagation()}
                    onchange={(e) => tick(f.path, e.currentTarget.checked)}
                  />
                </td>
                <td><button class="row-button" onclick={() => (picked = f)}>{f.name}</button></td>
                <td class="text-label hide-narrow">{f.media_type}</td>
                <td class="text-label">{size(f.size)}</td>
                <td class="text-label hide-narrow">{source(f)}</td>
                <td class="text-label hide-narrow">{f.conversation || t("common.untitled")}</td>
                <td class="text-label">{when(f.uploaded_at)}</td>
                <td class="row-actions">
                  <button
                    class="tool"
                    aria-label={t("files.deleteOne", { name: f.name })}
                    title={t("files.deleteOne", { name: f.name })}
                    disabled={deleting}
                    onclick={(e) => {
                      e.stopPropagation();
                      confirming = [f.path];
                    }}><Trash2 size={14} /></button
                  >
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
    {#if total > PAGE_SIZE}<Pager bind:page {total} size={PAGE_SIZE} />{/if}
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
  /* What's ticked, or the question before deleting it: between the toolbar and the table, so it stays in sight. */
  .action-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 10px 24px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
    background: color-mix(in srgb, var(--color-accent) 6%, transparent);
  }
  .action-bar.confirming {
    background: color-mix(in srgb, var(--color-danger) 8%, transparent);
  }
  .action-bar p {
    margin: 2px 0 0;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: none;
  }
  .actions .btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .data-table .check {
    width: 1px;
    padding-right: 8px;
  }
  .check input {
    display: block;
    margin: 0;
    cursor: pointer;
  }
  .data-table .row-actions {
    width: 1px;
  }
  tr.ticked {
    background: color-mix(in srgb, var(--color-accent) 5%, transparent);
  }
  .tool {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .tool:hover:not(:disabled) {
    color: var(--color-danger);
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
    .action-bar {
      flex-wrap: wrap;
    }
  }
</style>
