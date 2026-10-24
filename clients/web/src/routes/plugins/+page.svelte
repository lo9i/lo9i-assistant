<script lang="ts">
  import { keptKeys } from "$lib/keptKeys.svelte";
  import Download from "@lucide/svelte/icons/download";
  import GitBranch from "@lucide/svelte/icons/git-branch";
  import Puzzle from "@lucide/svelte/icons/puzzle";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import type { FoundServer } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import {
    type Plugin,
    byCategory,
    categoryLabel,
    categoryOf,
    describe,
    fromRepositories,
    iconOf,
    keyOf,
    kindOf,
    runsOf,
    hasNewer,
    sourceOf,
    updatable,
    versionOf,
  } from "$lib/plugins";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import PluginIcon from "$lib/ui/PluginIcon.svelte";
  import SearchField from "$lib/ui/SearchField.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import PluginUpdatesSwitch from "$lib/ui/settings/PluginUpdatesSwitch.svelte";
  import SettingsTabs from "$lib/ui/settings/SettingsTabs.svelte";
  import InstallDialog from "$lib/ui/repositories/InstallDialog.svelte";
  import PluginSetup from "$lib/ui/plugins/PluginSetup.svelte";
  import PluginUpdates from "$lib/ui/plugins/PluginUpdates.svelte";
  import RepositoryCheck from "$lib/ui/plugins/RepositoryCheck.svelte";
  import { type CheckState, type UpdateStep, checkRepositories, updateEach } from "$lib/pluginUpdates";
  import RepositoriesDialog from "$lib/ui/repositories/RepositoriesDialog.svelte";

  const { client, notices } = useDaemon();
  // Shown at once as the repositories offered it when last checked; installed or not is read fresh. Each visit
  // checks them again in the background: a check that finds something new saves it, announced as `plugins`.
  const listing = resource(async (c) => fromRepositories(await c.repositories.plugins(true)), ["plugins"]);
  const all = $derived(listing.data?.plugins);
  let managing = $state(false);

  let check = $state<CheckState>("idle");
  const checkNow = () =>
    checkRepositories(
      () => client.repositories.plugins(),
      (s) => (check = s),
    );
  // Once the list shows, so on a first visit, where showing it downloads the repositories, they aren't twice at once.
  let started = false;
  $effect(() => {
    if (listing.data && !started) {
      started = true;
      void checkNow();
    }
  });

  let picked = $state<string | null>(null);
  let query = $state("");
  // By name, description, kind or category; grouped by category.
  const shown = $derived(
    byCategory(
      (all ?? []).filter((p) =>
        `${p.name} ${describe(p)} ${kindOf(p)} ${categoryOf(p)}`.toLowerCase().includes(query.trim().toLowerCase()),
      ),
    ),
  );
  // A plugin that asks for values, while its dialog is open.
  let asking = $state<{ server: FoundServer; url: string } | null>(null);
  let removing = $state<Plugin | null>(null);
  let busy = $state(false);
  // Until one is picked: the first in the list.
  const plugin = $derived(all?.find((p) => keyOf(p) === picked) ?? shown[0]?.plugins[0]);

  async function act(action: () => Promise<unknown>, done: string): Promise<void> {
    busy = true;
    try {
      await action();
      notices.notify(done);
    } catch (e) {
      notices.report(e);
    } finally {
      busy = false;
    }
    listing.reload();
  }

  /** At once when it asks for nothing; otherwise a dialog for its values. */
  function install(p: Plugin): void {
    const url = p.repository.url || undefined;
    if (p.kind === "server" && p.server.fields.length) {
      asking = { server: p.server, url: p.repository.url };
      return;
    }
    void act(
      () =>
        p.kind === "server"
          ? client.repositories.install([], [{ name: p.name, values: {} }], url)
          : client.repositories.install([p.name], [], url),
      `Installed ${p.name}. The assistant uses it from your next message.`,
    );
  }

  const updateOne = (p: Plugin) => (p.kind === "server" ? client.mcp.updateFromRepository(p.name) : client.skills.updateInstalled(p.name));
  const update = (p: Plugin) => act(() => updateOne(p), `Updated ${p.name}.`);
  // Installed plugins the extras have a newer version of, for the Updates table.
  const newer = $derived((all ?? []).filter(hasNewer));

  // Each row's progress in the Updates table, by keyOf, from Update all or Update selected until the next.
  let steps = $state<Record<string, UpdateStep>>({});

  async function updateMany(picked: Plugin[]): Promise<void> {
    busy = true;
    steps = {};
    const { updated } = await updateEach(
      picked,
      updateOne,
      (key, step) => (steps = { ...steps, [key]: step }),
      (e) => notices.report(e),
    );
    busy = false;
    if (updated.length) notices.notify(`Updated ${updated.join(", ")}.`);
    listing.reload();
  }
  const remove = (p: Plugin, deleteData: boolean) =>
    act(
      async () => keptKeys.ask(await (p.kind === "server" ? client.mcp.remove(p.name, deleteData) : client.skills.delete(p.name))),
      `Removed ${p.name}.`,
    );
</script>

<!-- A settings tab of its own page: the list and details need the full height. -->
<TopBar title="Settings" />

<div class="tabs-bar"><SettingsTabs active="plugins" /><PluginUpdatesSwitch /></div>

<div class="screen">
  <div class="main">
    {#if newer.length}<PluginUpdates plugins={newer} {busy} {steps} onupdate={updateMany} />{/if}
    <section class="table-card surface--glass">
      <header class="toolbar">
        <div>
          <h2 class="text-heading">Plugins</h2>
          <p class="text-meta">
            MCP servers, chat channels and skills from the official extras and your repositories. Click one to see it on the right.
          </p>
        </div>
        <div class="tools">
          <SearchField bind:value={query} label="Search plugins" />
          {#if all}<span class="pill">{all.length}</span>{/if}
          <RepositoryCheck {check} checked={listing.data?.checked ?? ""} />
          <button class="btn btn--ghost btn--sm" title="Repositories plugins are listed from" onclick={() => (managing = true)}
            ><GitBranch size={14} />Repositories</button
          >
          <button
            class="btn btn--ghost btn--sm"
            title="Check the repositories for a newer version"
            disabled={check === "checking"}
            onclick={() => void checkNow()}><RefreshCw size={14} /></button
          >
        </div>
      </header>
      <div class="scroll">
        {#if listing.error}
          <p class="error-text pad">{listing.error}</p>
        {:else if all === undefined}
          <p class="text-meta pad">Looking at the repositories…</p>
        {:else}
          {#each listing.data?.errors ?? [] as error (error)}<p class="error-text pad">{error}</p>{/each}
          {#if all.length === 0}
            <EmptyState icon={Puzzle} title="No plugins" text="The repositories offer none yet." />
          {:else}
            <table class="data-table">
              <thead><tr><th>Plugin</th><th class="hide-narrow">Kind</th><th>Version</th><th>State</th></tr></thead>
              <tbody>
                {#each shown as group (group.category)}
                  <tr class="category"><th colspan="4" class="micro-label">{categoryLabel(group.category)}</th></tr>
                  {#each group.plugins as p (keyOf(p))}
                    <tr class:selected={plugin && keyOf(p) === keyOf(plugin)} onclick={() => (picked = keyOf(p))}>
                      <td>
                        <button class="row-button" onclick={() => (picked = keyOf(p))}
                          ><span class="plugin-icon"><PluginIcon icon={iconOf(p)} size={16} /></span>{p.name}</button
                        >
                        <span class="source" class:official={p.repository.official}>{sourceOf(p)}</span>
                        {#if describe(p)}<p class="text-caption row-description">{describe(p)}</p>{/if}
                      </td>
                      <td class="hide-narrow">{kindOf(p)}</td>
                      <td>{versionOf(p)}</td>
                      <td>
                        <span class="state"
                          ><span class="status-dot" style:--tone={p.installed ? "var(--color-success)" : undefined}></span>{p.installed
                            ? "Installed"
                            : "Not installed"}</span
                        >
                      </td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="4" class="text-meta">No matches.</td></tr>
                {/each}
              </tbody>
            </table>
          {/if}
        {/if}
      </div>
    </section>
  </div>

  <div class="column">
    {#if plugin}
      <section class="details surface--glass">
        <header>
          <h2 class="text-heading title"><PluginIcon icon={iconOf(plugin)} size={22} />{plugin.name}</h2>
        </header>
        {#if describe(plugin)}<p>{describe(plugin)}</p>{/if}
        <dl>
          <dt class="micro-label">Source</dt>
          <dd>{plugin.repository.official ? "Official: the assistant's extras" : `${plugin.repository.name}, not official`}</dd>
          <dt class="micro-label">Category</dt>
          <dd>{categoryLabel(categoryOf(plugin))}</dd>
          <dt class="micro-label">Kind</dt>
          <dd>{kindOf(plugin)}</dd>
          <dt class="micro-label">Version</dt>
          <dd>{versionOf(plugin)}</dd>
          {#if plugin.kind === "server"}
            <dt class="micro-label">Runs</dt>
            <dd>{runsOf(plugin.server)}</dd>
            {#if plugin.server.fields.length}
              <dt class="micro-label">Asks for</dt>
              <dd>{plugin.server.fields.map((f) => f.label).join(", ")}</dd>
            {/if}
          {:else if plugin.skill.files.length}
            <dt class="micro-label">Files</dt>
            <dd>{plugin.skill.files.join(", ")}</dd>
          {/if}
          <dt class="micro-label">State</dt>
          <dd>{plugin.installed ? "Installed" : "Not installed"}</dd>
        </dl>
        <div class="actions">
          {#if plugin.installed}
            {#if updatable(plugin)}
              <button class="btn btn--neutral btn--sm" disabled={busy} onclick={() => plugin && update(plugin)}
                ><RefreshCw size={14} />Update</button
              >
            {/if}
            <button class="btn btn--danger btn--sm" disabled={busy} onclick={() => (removing = plugin ?? null)}
              ><Trash2 size={14} />Remove</button
            >
          {:else}
            <button class="btn btn--primary btn--sm" disabled={busy} onclick={() => plugin && install(plugin)}
              ><Download size={14} />Install</button
            >
          {/if}
        </div>
        {#if plugin.installed && plugin.kind === "server"}<PluginSetup server={plugin.server} />{/if}
      </section>
    {/if}
  </div>
</div>

{#if asking}
  <InstallDialog
    server={asking.server}
    url={asking.url || undefined}
    onclose={(installed) => {
      asking = null;
      if (installed) notices.notify(`Installed ${installed.join(", ")}. The assistant uses it from your next message.`);
      listing.reload();
    }}
  />
{/if}

{#if managing}
  <RepositoriesDialog
    onclose={(changed) => {
      managing = false;
      if (changed) listing.reload();
    }}
  />
{/if}

{#if removing}
  {@const p = removing}
  <Confirm
    title="Remove {p.name}?"
    text={p.kind === "server"
      ? "Its tools, skill and page go. Its data stays, for installing it again, unless you delete it too."
      : "The assistant won't be able to use this skill any more."}
    action="Remove"
    option={p.kind === "server" ? "Also delete its data (can't be undone)" : undefined}
    onanswer={(yes, deleteData) => {
      // `p` follows `removing`: read it before clearing that.
      const plugin = p;
      removing = null;
      if (yes) void remove(plugin, deleteData);
    }}
  />
{/if}

<style>
  .tabs-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    max-width: 1600px;
    margin: 0 auto;
    padding: 0 16px;
  }
  .screen {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 16px;
    height: calc(100dvh - 76px - 34px);
    max-width: 1600px;
    margin: 0 auto;
  }
  .main {
    flex: 3 1 0;
    min-width: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .table-card {
    min-width: 0;
    min-height: 0;
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
  .toolbar p {
    margin: 4px 0 0;
  }
  .tools {
    display: flex;
    align-items: center;
    gap: 8px;
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
    margin: 0;
  }
  tr {
    cursor: pointer;
  }
  tr.category {
    cursor: default;
  }
  tr.category th {
    padding-top: 16px;
    text-align: left;
  }
  tr.selected {
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
  }
  tr.selected td:first-child {
    box-shadow: inset 3px 0 0 var(--color-accent);
  }
  .row-button {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    cursor: pointer;
  }
  .plugin-icon {
    display: inline-flex;
    color: var(--color-text-muted);
  }
  .title {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .source {
    margin-left: 8px;
    padding: 1px 6px;
    border-radius: 999px;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
    border: 1px solid var(--color-border);
  }
  .source.official {
    color: var(--color-success);
    border-color: color-mix(in srgb, var(--color-success) 40%, transparent);
  }
  .state {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .details {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
  }
  .details p {
    margin: 0;
  }
  .row-description {
    margin: 2px 0 0;
  }
  .details header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
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
    overflow-wrap: anywhere;
  }
  .actions {
    display: flex;
    gap: 8px;
  }
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
      align-items: stretch;
      height: auto;
    }
    .main,
    .table-card,
    .column {
      flex: none;
    }
  }
</style>
