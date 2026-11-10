<script lang="ts">
  import FileUp from "@lucide/svelte/icons/file-up";
  import type { ImportReport } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { formatDate, t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";
  import SecretInput from "../SecretInput.svelte";
  import MoveOverSsh from "./MoveOverSsh.svelte";
  import MovePart from "./MovePart.svelte";

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

  const canExport = $derived(!exporting && !!exportPassword);
  const canImport = $derived(!importing && !!file && !!importPassword);

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
  <MovePart title={t("move.export")} caption={t("move.exportHint")} onsubmit={() => void exportData()}>
    <div class="fields inline">
      <SecretInput bind:value={exportPassword} label={t("move.password")} placeholder={t("move.password")} required />
      <button class="btn" class:btn--primary={canExport} class:btn--neutral={!canExport} type="submit" disabled={!canExport}>
        {exporting ? t("move.exporting") : t("move.export")}
      </button>
    </div>
    {#if exported}<p class="text-meta">{exported}</p>{/if}
    {#if exportError}<p class="error-text">{exportError}</p>{/if}
  </MovePart>

  <MovePart title={t("move.import")} caption={t("move.importHint")} onsubmit={() => void importData()}>
    <div class="fields pair">
      <label class="input picker" class:picked={file}>
        <input class="hidden" type="file" aria-label={t("move.file")} onchange={(e) => (file = e.currentTarget.files?.[0] ?? null)} />
        <FileUp size={16} />
        <span class="name">{file ? file.name : t("move.chooseFile")}</span>
      </label>
      <SecretInput bind:value={importPassword} label={t("move.password")} placeholder={t("move.password")} required />
    </div>
    <div class="actions">
      <label class="check" title={t("move.replaceKept")}><input type="checkbox" bind:checked={replace} />{t("move.replace")}</label>
      <button class="btn" class:btn--primary={canImport} class:btn--neutral={!canImport} type="submit" disabled={!canImport}>
        {importing ? t("move.importing") : t("move.import")}
      </button>
    </div>
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
  </MovePart>
</SettingsCard>

<style>
  /* The password takes the room the button leaves. */
  .inline {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .pair {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
  @container (max-width: 420px) {
    .pair {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  /* The file input itself stays for the keyboard and screen readers; the field over it shows it in the app's language. */
  .picker {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .picker.picked {
    color: var(--color-text-primary);
  }
  .picker:focus-within {
    border-color: color-mix(in srgb, var(--color-accent) 62%, var(--color-border));
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-accent) 14%, transparent);
  }
  .hidden {
    position: absolute;
    inset: 0;
    width: 100%;
    opacity: 0;
    cursor: pointer;
  }
  .name {
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
