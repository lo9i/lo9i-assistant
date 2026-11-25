<script lang="ts">
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import Trash from "@lucide/svelte/icons/trash-2";
  import { untrack } from "svelte";
  import type { BackupModelAdd, BackupModelStatus, ModelOption, ModelProvider } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";
  import SecretInput from "../SecretInput.svelte";

  // The backup models (core/llm/backups.py), tried in order when the main model fails on the provider's side. One on
  // the main model's provider takes its values (its key) where it has none of its own.
  const { client } = useDaemon();
  const loaded = resource((c) => c.model.backups(), ["settings"]);
  const main = resource((c) => c.model.status(), ["settings"]);
  const providers = resource((c) => c.model.providers(), ["settings"]);
  let form = $state<BackupModelAdd>({ provider: "", values: {}, model: "" });
  let options = $state<ModelOption[]>([]);
  let message = $state("");
  let busy = $state(false);
  const provider = $derived<ModelProvider | undefined>(providers.data?.find((p) => p.id === form.provider));
  const onMain = $derived(main.data !== undefined && form.provider === main.data.provider);

  // The form starts on the main model's provider, so a backup on the same account needs no key.
  $effect(() => {
    if (!form.provider && main.data) form = { provider: main.data.provider, values: {}, model: "" };
  });

  async function loadModels(): Promise<void> {
    if (!form.provider) return;
    try {
      options = await client.model.available(form.provider, form.values);
    } catch {
      options = [];
    }
  }

  $effect(() => {
    void form.provider;
    untrack(loadModels);
  });

  function choose(id: string): void {
    form = { provider: id, values: {}, model: "" };
  }

  function providerName(id: string): string {
    return providers.data?.find((p) => p.id === id)?.name ?? id;
  }

  async function act(change: () => Promise<BackupModelStatus[]>): Promise<void> {
    busy = true;
    try {
      await change();
      message = "";
    } catch (e) {
      message = describe(e);
    } finally {
      busy = false;
    }
    loaded.reload();
  }

  async function add(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    message = t("backupModels.adding");
    try {
      await client.model.addBackup(form);
      message = t("backupModels.added");
      form = { ...form, values: {}, model: "" };
    } catch (e) {
      message = describe(e);
    } finally {
      busy = false;
    }
    loaded.reload();
  }

  function move(list: BackupModelStatus[], index: number, by: number): Promise<BackupModelStatus[]> {
    const ids = list.map((b) => b.id);
    [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
    return client.model.orderBackups(ids);
  }
</script>

<SettingsCard id="backup-models" title={t("backupModels.title")} sub={t("backupModels.sub")}>
  {#if loaded.data === undefined}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
  {:else}
    {#if loaded.data.length === 0}
      <p class="text-meta">{t("backupModels.none")}</p>
    {:else}
      <ol class="list">
        {#each loaded.data as b, i (b.id)}
          {@const list = loaded.data}
          <li class="row-item">
            <span class="grow">
              <span>{i + 1}. {b.model}</span>
              <span class="text-caption"
                >{providerName(b.provider)}{#if b.uses_main_values && !b.secrets_set.length}
                  · {t("backupModels.mainKey")}{/if}</span
              >
            </span>
            <button
              class="btn btn--icon"
              title={t("backupModels.moveUp")}
              aria-label={t("backupModels.moveUp")}
              disabled={busy || i === 0}
              onclick={() => act(() => move(list, i, -1))}><ArrowUp size={16} /></button
            >
            <button
              class="btn btn--icon"
              title={t("backupModels.moveDown")}
              aria-label={t("backupModels.moveDown")}
              disabled={busy || i === list.length - 1}
              onclick={() => act(() => move(list, i, 1))}><ArrowDown size={16} /></button
            >
            <button
              class="btn btn--icon"
              title={t("backupModels.remove", { model: b.model })}
              aria-label={t("backupModels.remove", { model: b.model })}
              disabled={busy}
              onclick={() => act(() => client.model.removeBackup(b.id))}><Trash size={16} /></button
            >
          </li>
        {/each}
      </ol>
    {/if}
    <form class="fields" onsubmit={add}>
      <span class="text-label">{t("backupModels.add")}</span>
      <select class="input" value={form.provider} aria-label={t("model.provider")} onchange={(e) => choose(e.currentTarget.value)}>
        {#each providers.data ?? [] as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
      </select>
      {#if provider}
        {#if onMain}<span class="text-caption">{t("backupModels.usesMain")}</span>{/if}
        {#each provider.fields as f (f.key)}
          <label class="fields">
            <span class="text-label">{f.label}</span>
            {#if f.options?.length}
              <select class="input" aria-label={f.label} bind:value={() => form.values[f.key] || "", (v) => (form.values[f.key] = v)}>
                {#if onMain}<option value="">—</option>{/if}
                {#each f.options as o (o)}<option value={o}>{o}</option>{/each}
              </select>
            {:else if f.secret}
              <SecretInput
                label={f.label}
                placeholder={f.required && !onMain ? f.label : t("model.optional", { label: f.label })}
                bind:value={form.values[f.key]}
                onchange={loadModels}
              />
            {:else}
              <input
                class="input"
                autocomplete="off"
                placeholder={f.required && !onMain ? f.label : t("model.optional", { label: f.label })}
                aria-label={f.label}
                bind:value={form.values[f.key]}
              />
            {/if}
          </label>
        {/each}
      {/if}
      <label class="fields">
        <span class="text-label">{t("backupModels.model")}</span>
        {#if options.length}
          <select class="input" aria-label={t("backupModels.model")} bind:value={form.model}>
            <option value="" disabled>—</option>
            {#each [...options].sort((a, b) => a.name.localeCompare(b.name)) as m (m.id)}<option value={m.id}>{m.name}</option>{/each}
          </select>
        {:else}
          <input class="input" aria-label={t("backupModels.model")} bind:value={form.model} />
        {/if}
      </label>
      <div class="row">
        <button class="btn btn--primary" type="submit" disabled={busy || !form.model.trim()}>{t("backupModels.add")}</button>
      </div>
    </form>
  {/if}
  {#if message}<p class="text-meta">{message}</p>{/if}
</SettingsCard>

<style>
  .fields {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .row-item {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .grow {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .row {
    display: flex;
    gap: 8px;
  }
  p {
    margin: 0;
  }
</style>
