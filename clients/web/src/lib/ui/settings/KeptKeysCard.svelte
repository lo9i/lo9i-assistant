<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describeKept, keptName } from "$lib/keptKeys.svelte";
  import type { KeptKeys } from "$lib/api/types";
  import Confirm from "../Confirm.svelte";
  import SettingsCard from "../Card.svelte";

  // What removed plugins left kept, encrypted on the assistant's computer: their keys, used again when one is
  // installed again, and private repositories' tokens nothing needs any more. Deleting is for good.
  const { client, notices } = useDaemon();
  const kept = resource((c) => c.repositories.keptKeys(), ["plugins", "mcp", "skills", "settings"]);
  let deleting = $state<KeptKeys | null>(null);

  async function remove(entry: KeptKeys): Promise<void> {
    try {
      await client.repositories.forgetKeys(entry);
      notices.notify(
        entry.plugin
          ? t("keptKeys.deletedKeys", { plugin: entry.plugin })
          : t("keptKeys.deletedToken", { repository: entry.repository_name }),
      );
    } catch (e) {
      notices.report(e);
    }
    kept.reload();
  }
</script>

<SettingsCard id="kept-keys" title={t("keptKeys.title")} sub={t("keptKeys.sub")}>
  {#snippet status()}
    <span class="pill">{kept.data === undefined ? "…" : kept.data.length || t("keptKeys.none")}</span>
  {/snippet}
  {#if kept.data === undefined}
    <p class="text-meta">{kept.error ?? t("common.loading")}</p>
  {:else if !kept.data.length}
    <p class="text-meta">{t("keptKeys.nothing")}</p>
  {:else}
    <ul class="list">
      {#each kept.data as entry (entry.plugin + entry.repository)}
        <li>
          <div class="text">
            <strong>{keptName(entry)}</strong>
            <span class="text-meta">{entry.plugin ? describeKept(entry) : t("keptKeys.unneeded")}</span>
          </div>
          <button class="btn btn--danger btn--sm" onclick={() => (deleting = entry)}>{t("common.delete")}</button>
        </li>
      {/each}
    </ul>
  {/if}
</SettingsCard>

{#if deleting}
  {@const entry = deleting}
  <Confirm
    title={entry.plugin
      ? t("keptKeys.deleteKeysTitle", { plugin: entry.plugin })
      : t("keptKeys.deleteTokenTitle", { repository: entry.repository_name })}
    text={entry.plugin ? t("keptKeys.deleteKeysText") : t("keptKeys.deleteTokenText")}
    action={t("common.delete")}
    onanswer={(yes) => {
      // Before clearing `deleting`: `entry` is derived from it, so it would read null after.
      if (yes) void remove(entry);
      deleting = null;
    }}
  />
{/if}

<style>
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .list li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .text span {
    overflow-wrap: anywhere;
  }
</style>
