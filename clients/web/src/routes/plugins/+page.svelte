<script lang="ts">
  import Download from "@lucide/svelte/icons/download";
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
    hasSettings,
    keyOf,
    kindOf,
    pluginsOf,
    runsOf,
    updatable,
    versionOf,
  } from "$lib/plugins";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import SearchField from "$lib/ui/SearchField.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import PluginUpdatesSwitch from "$lib/ui/settings/PluginUpdatesSwitch.svelte";
  import SettingsTabs from "$lib/ui/settings/SettingsTabs.svelte";
  import InstallDialog from "$lib/ui/repositories/InstallDialog.svelte";
  import ChannelSetup from "$lib/ui/plugins/ChannelSetup.svelte";
  import EmailAccounts from "$lib/ui/plugins/EmailAccounts.svelte";
  import EmailRecipients from "$lib/ui/plugins/EmailRecipients.svelte";

  const { client, notices } = useDaemon();
  // The extras are downloaded to list them, so this reloads after an action here or on refresh,
  // not on every server's status change.
  const plugins = resource(async (c) => pluginsOf(await c.repositories.browse()), []);
  // Installed chat channels' setup; the `channels` event comes when one connects or changes its items.
  const channels = resource((c) => c.channels.list(), ["channels"]);

  let picked = $state<string | null>(null);
  let query = $state("");
  // By name, description, kind or category; grouped by category.
  const shown = $derived(
    byCategory(
      (plugins.data ?? []).filter((p) =>
        `${p.name} ${describe(p)} ${kindOf(p)} ${categoryOf(p)}`.toLowerCase().includes(query.trim().toLowerCase()),
      ),
    ),
  );
  // A plugin that asks for values, while its dialog is open.
  let asking = $state<FoundServer | null>(null);
  let removing = $state<Plugin | null>(null);
  let busy = $state(false);
  // A category with settings shared by its plugins, when its name was picked.
  const category = $derived(picked?.startsWith("category:") ? picked.slice("category:".length) : null);
  // Until one is picked: the first in the list.
  const plugin = $derived(category ? undefined : (plugins.data?.find((p) => keyOf(p) === picked) ?? shown[0]?.plugins[0]));
  const channel = $derived(plugin?.installed && plugin.kind === "server" ? channels.data?.find((c) => c.name === plugin.name) : undefined);

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
    plugins.reload();
  }

  /** At once when it asks for nothing; otherwise a dialog for its values. */
  function install(p: Plugin): void {
    if (p.kind === "server" && p.server.fields.length) {
      asking = p.server;
      return;
    }
    void act(
      () =>
        p.kind === "server" ? client.repositories.install([], [{ name: p.name, values: {} }]) : client.repositories.install([p.name], []),
      `Installed ${p.name}. The assistant uses it from your next message.`,
    );
  }

  const update = (p: Plugin) =>
    act(
      () => (p.kind === "server" ? client.mcp.updateFromRepository(p.name) : client.skills.updateInstalled(p.name)),
      `Updated ${p.name}.`,
    );
  const remove = (p: Plugin, deleteData: boolean) =>
    act(() => (p.kind === "server" ? client.mcp.remove(p.name, deleteData) : client.skills.delete(p.name)), `Removed ${p.name}.`);
</script>

<!-- A settings tab of its own page: the list and details need the full height. -->
<TopBar title="Settings" />

<div class="tabs-bar"><SettingsTabs active="plugins" /><PluginUpdatesSwitch /></div>

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Plugins</h2>
        <p class="text-meta">MCP servers, chat channels and skills from the assistant's extras. Click one to see it on the right.</p>
      </div>
      <div class="tools">
        <SearchField bind:value={query} label="Search plugins" />
        {#if plugins.data}<span class="pill">{plugins.data.length}</span>{/if}
        <button class="btn btn--ghost btn--sm" title="Check the extras for a newer version" onclick={() => plugins.reload()}
          ><RefreshCw size={14} /></button
        >
      </div>
    </header>
    <div class="scroll">
      {#if plugins.error}
        <p class="error-text pad">{plugins.error}</p>
      {:else if plugins.data === undefined}
        <p class="text-meta pad">Looking at the extras…</p>
      {:else}
        {#if plugins.data.length === 0}
          <EmptyState icon={Puzzle} title="No plugins" text="The extras offer none yet." />
        {:else}
          <table class="data-table">
            <thead><tr><th>Plugin</th><th class="hide-narrow">Kind</th><th>Version</th><th>State</th></tr></thead>
            <tbody>
              {#each shown as group (group.category)}
                {#if hasSettings(group.category)}
                  <tr class="category" class:selected={category === group.category} onclick={() => (picked = `category:${group.category}`)}>
                    <th colspan="4" class="micro-label">
                      <button class="row-button" onclick={() => (picked = `category:${group.category}`)}
                        >{categoryLabel(group.category)} · settings</button
                      >
                    </th>
                  </tr>
                {:else}
                  <tr class="category"><th colspan="4" class="micro-label">{categoryLabel(group.category)}</th></tr>
                {/if}
                {#each group.plugins as p (keyOf(p))}
                  <tr class:selected={plugin && keyOf(p) === keyOf(plugin)} onclick={() => (picked = keyOf(p))}>
                    <td>
                      <button class="row-button" onclick={() => (picked = keyOf(p))}>{p.name}</button>
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

  <div class="column">
    {#if plugin}
      <section class="details surface--glass">
        <header><h2 class="text-heading">{plugin.name}</h2></header>
        {#if describe(plugin)}<p>{describe(plugin)}</p>{/if}
        <dl>
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
        {#if channel}<ChannelSetup {channel} />{/if}
        {#if plugin.installed && plugin.kind === "server" && plugin.server.email}
          <EmailAccounts plugin={plugin.name} title="Accounts" />
        {/if}
      </section>
    {:else if category === "communications"}
      <section class="details surface--glass">
        <header><h2 class="text-heading">Communications</h2></header>
        <p>Settings shared by the email and chat plugins.</p>
        <EmailRecipients />
        <EmailAccounts plugin="" title="Other accounts (servers entered by hand)" />
      </section>
    {/if}
  </div>
</div>

{#if asking}
  <InstallDialog
    server={asking}
    onclose={(installed) => {
      asking = null;
      if (installed) notices.notify(`Installed ${installed.join(", ")}. The assistant uses it from your next message.`);
      plugins.reload();
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
      removing = null;
      if (yes) void remove(p, deleteData);
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
    padding: 16px 16px 0;
  }
  .screen {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 16px;
    height: calc(100dvh - 76px - 50px);
    max-width: 1600px;
    margin: 0 auto;
  }
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
  tr.category:not(:has(button)) {
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
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    cursor: pointer;
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
    .table-card,
    .column {
      flex: none;
    }
  }
</style>
