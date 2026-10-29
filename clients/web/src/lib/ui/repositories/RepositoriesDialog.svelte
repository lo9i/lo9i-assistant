<script lang="ts">
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import type { Repository } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import Confirm from "../Confirm.svelte";
  import Modal from "../Modal.svelte";
  import SecretInput from "../SecretInput.svelte";

  // The repositories Plugins lists plugins from. The assistant's extras are built in and the only
  // official one; others are added by their https:// address and removed here, which leaves what was
  // installed from them. A private one is added with a token that can read it, which goes straight to
  // the daemon and is kept encrypted. `onclose` says whether the list changed, so Plugins reads them again.
  type Props = { onclose: (changed: boolean) => void };
  let { onclose }: Props = $props();
  const { client, notices } = useDaemon();
  const repositories = resource((c) => c.repositories.list(), ["settings"]);

  let url = $state("");
  let token = $state("");
  let busy = $state(false);
  let error = $state("");
  let changed = $state(false);
  let removing = $state<Repository | null>(null);

  async function add(): Promise<void> {
    if (!url.trim()) return;
    busy = true;
    try {
      const added = await client.repositories.add(url.trim(), token.trim());
      notices.notify(t("repositories.added", { name: added.name }));
      url = "";
      token = "";
      error = "";
      changed = true;
      repositories.reload();
    } catch (e) {
      error = describe(e);
    } finally {
      busy = false;
    }
  }

  async function remove(repository: Repository): Promise<void> {
    try {
      await client.repositories.remove(repository.url);
      notices.notify(t("repositories.removed", { name: repository.name }));
      changed = true;
    } catch (e) {
      notices.report(e);
    }
    repositories.reload();
  }
</script>

<Modal title={t("repositories.title")} description={t("repositories.description")} onclose={() => onclose(changed)}>
  {#if repositories.error}
    <p class="error-text">{repositories.error}</p>
  {:else if repositories.data}
    <ul>
      {#each repositories.data as r (r.url)}
        <li>
          <div>
            <span class="name">{r.name}</span>
            {#if r.official}<span class="badge official">{t("plugins.official")}</span>{/if}
            {#if r.private}<span class="badge">{t("repositories.private")}</span>{/if}
            <p class="text-caption">{r.url}</p>
          </div>
          {#if !r.official}
            <button class="btn btn--ghost btn--sm" title={t("repositories.removeName", { name: r.name })} onclick={() => (removing = r)}
              ><Trash2 size={14} /></button
            >
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
  <form
    onsubmit={(e) => {
      e.preventDefault();
      void add();
    }}
  >
    <input class="input" bind:value={url} placeholder="https://github.com/you/your-plugins" aria-label={t("repositories.address")} />
    <SecretInput bind:value={token} label={t("repositories.tokenLabel")} placeholder={t("repositories.tokenPlaceholder")} />
    <button class="btn btn--primary" disabled={busy || !url.trim()}>{busy ? t("repositories.reading") : t("repositories.add")}</button>
  </form>
  <p class="text-caption">{t("repositories.hint")}</p>
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onclose(changed)}>{t("common.close")}</button>
  {/snippet}
</Modal>

{#if removing}
  {@const r = removing}
  <Confirm
    title={t("repositories.removeTitle", { name: r.name })}
    text={r.private ? t("repositories.removePrivateText") : t("repositories.removeText")}
    action={t("common.remove")}
    onanswer={(yes) => {
      // Before clearing `removing`: `r` is derived from it, so it would read null after.
      if (yes) void remove(r);
      removing = null;
    }}
  />
{/if}

<style>
  ul {
    list-style: none;
    margin: 0 0 16px;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  li p {
    margin: 2px 0 0;
    overflow-wrap: anywhere;
  }
  .name {
    font-weight: 500;
  }
  .badge {
    margin-left: 8px;
    padding: 1px 6px;
    border-radius: 999px;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
    border: 1px solid var(--color-border);
  }
  .badge.official {
    color: var(--color-success);
    border-color: color-mix(in srgb, var(--color-success) 40%, transparent);
  }
  form {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  form > :global(*) {
    flex: 1 1 200px;
  }
  form > button {
    flex: 0 0 auto;
  }
  .text-caption {
    margin: 4px 0 0;
  }
</style>
