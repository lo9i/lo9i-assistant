<script lang="ts">
  // Updating lo9i, in the Assistant card: what's new upstream, checking for it and installing it. Installing restarts
  // the daemon, which the card's EndingDialog waits for.
  import { Download, LoaderCircle, SearchCheck } from "@lucide/svelte";
  import type { UpdateStatus } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { canInstall, updateLine } from "$lib/updates";
  import Confirm from "../Confirm.svelte";
  import SettingRow from "./SettingRow.svelte";

  const { client, notices } = useDaemon();
  // Each change of an update's state comes as an `update` event.
  const update = resource((c) => c.system.updateStatus(), ["update"]);
  let confirming = $state(false);
  let checking = $state(false);

  async function check(): Promise<void> {
    checking = true;
    try {
      await client.system.checkForUpdate();
      await update.reload();
    } catch (e) {
      notices.report(e);
    } finally {
      checking = false;
    }
  }

  async function install(): Promise<void> {
    try {
      await client.system.update();
    } catch (e) {
      notices.report(e);
    }
  }

  function busy(status: UpdateStatus): boolean {
    return checking || ["checking", "updating", "restarting"].includes(status.state);
  }
</script>

{#if update.data}
  {@const u = update.data}
  <section class="update">
    <SettingRow label={t("host.updates")}>
      {#snippet hint()}
        <span class="line" class:error-text={u.state === "failed"}>
          {#if busy(u)}<LoaderCircle size={12} class="spin" aria-hidden="true" />{/if}
          {updateLine(u)}
        </span>
      {/snippet}
      {#if u.installed_from === "git"}
        <button class="btn btn--sm" onclick={check} disabled={busy(u)}>
          <SearchCheck size={14} />
          {t("host.check")}
        </button>
      {/if}
      {#if canInstall(u)}
        <button class="btn btn--sm btn--primary" onclick={() => (confirming = true)} disabled={busy(u)}>
          <Download size={14} />
          {t("host.updateAndRestart")}
        </button>
      {/if}
    </SettingRow>
    {#if u.new.length && u.state !== "restarting"}
      <ul class="commits">
        {#each u.new as commit (commit.sha)}
          <li><code>{commit.sha.slice(0, 7)}</code> {commit.subject}</li>
        {/each}
      </ul>
    {/if}
  </section>
{/if}

{#if confirming}
  <Confirm
    title={t("host.updateTitle")}
    text={t("host.updateText")}
    action={t("common.update")}
    onanswer={(yes) => {
      confirming = false;
      if (yes) void install();
    }}
  />
{/if}

<style>
  .update {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .line {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .line :global(.spin) {
    animation: spin 1s linear infinite;
  }
  .commits {
    margin: 0;
    padding: 0;
    list-style: none;
    max-height: 180px;
    overflow-y: auto;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
  }
  .commits li {
    padding: 2px 0;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .line :global(.spin) {
      animation: none;
    }
  }
</style>
