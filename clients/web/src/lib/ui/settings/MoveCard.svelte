<script lang="ts">
  import type { ImportReport } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { formatDate, t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";
  import SecretInput from "../SecretInput.svelte";
  import MoveOverSsh from "./MoveOverSsh.svelte";

  // Moving lo9i to another computer (src/lo9i/core/migration/): straight there over SSH (MoveOverSsh), or by hand: the
  // export downloads here, sealed with a password; the import uploads one, and the daemon restarts to move it into
  // place, saying what has to be set up again.
  const { client } = useDaemon();

  let exportPassword = $state("");
  let exporting = $state(false);
  let exported = $state("");
  let exportError = $state("");

  let file = $state<File | null>(null);
  let importPassword = $state("");
  let replace = $state(false);
  let importing = $state(false);
  let report = $state<ImportReport | null>(null);
  let importError = $state("");

  async function exportData(): Promise<void> {
    exporting = true;
    exportError = exported = "";
    try {
      const ready = await client.system.exportData(exportPassword);
      download(ready.url, ready.name);
      exported = t("move.exported", { name: ready.name });
      exportPassword = "";
    } catch (e) {
      exportError = describe(e);
    } finally {
      exporting = false;
    }
  }

  /** The browser follows the link itself and saves the file as it comes, never holding it whole. */
  function download(url: string, name: string): void {
    Object.assign(document.createElement("a"), { href: url, download: name }).click();
  }

  async function importData(): Promise<void> {
    if (!file) return;
    importing = true;
    importError = "";
    report = null;
    try {
      report = await client.system.importData(file, importPassword, replace);
      importPassword = "";
    } catch (e) {
      importError = describe(e);
    } finally {
      importing = false;
    }
  }
</script>

<SettingsCard id="move" title={t("move.title")} sub={t("move.sub")}>
  <MoveOverSsh />
  <form
    class="part"
    onsubmit={(e) => {
      e.preventDefault();
      void exportData();
    }}
  >
    <span class="micro-label">{t("move.export")}</span>
    <div class="row">
      <SecretInput bind:value={exportPassword} label={t("move.password")} placeholder={t("move.password")} required />
      <button class="btn btn--primary" type="submit" disabled={exporting || !exportPassword}>
        {exporting ? t("move.exporting") : t("move.export")}
      </button>
    </div>
    <span class="text-caption">{t("move.exportHint")}</span>
    {#if exported}<p class="text-meta">{exported}</p>{/if}
    {#if exportError}<p class="error-text">{exportError}</p>{/if}
  </form>

  <form
    class="part"
    onsubmit={(e) => {
      e.preventDefault();
      void importData();
    }}
  >
    <span class="micro-label">{t("move.import")}</span>
    <input class="input" type="file" aria-label={t("move.file")} onchange={(e) => (file = e.currentTarget.files?.[0] ?? null)} />
    <div class="row">
      <SecretInput bind:value={importPassword} label={t("move.password")} placeholder={t("move.password")} required />
      <button class="btn" type="submit" disabled={importing || !file || !importPassword}>
        {importing ? t("move.importing") : t("move.import")}
      </button>
    </div>
    <label class="check"><input type="checkbox" bind:checked={replace} />{t("move.replace")}</label>
    {#if importError}<p class="error-text">{importError}</p>{/if}
    {#if report}
      <p class="text-meta">
        {t("move.imported", { host: report.host, system: report.system, when: formatDate(report.exported_at) })}
        {report.waiting_for_runs ? t("move.restartsAfter", { count: report.waiting_for_runs }) : t("move.restarts")}
      </p>
      <span class="micro-label">{t("move.toRedo")}</span>
      <ul class="redo">
        {#each report.to_redo as item (item)}<li>{item}</li>{/each}
      </ul>
    {/if}
  </form>
</SettingsCard>

<style>
  .part {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .text-meta,
  .text-caption {
    margin: 0;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--font-size-sm);
    cursor: pointer;
  }
  .redo {
    margin: 0;
    padding-left: 20px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: var(--font-size-sm);
  }
</style>
