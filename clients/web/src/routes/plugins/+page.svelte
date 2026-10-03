<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import Download from "@lucide/svelte/icons/download";
  import Plus from "@lucide/svelte/icons/plus";
  import Puzzle from "@lucide/svelte/icons/puzzle";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import X from "@lucide/svelte/icons/x";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe as describeError } from "$lib/notices";
  import { type Plugin, describe, keyOf, kindOf, pluginsOf, shortRepository } from "$lib/plugins";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import AddRepositoryDialog from "$lib/ui/repositories/AddRepositoryDialog.svelte";
  import InstallDialog from "$lib/ui/repositories/InstallDialog.svelte";

  const { client, notices } = useDaemon();
  const repositories = resource((c) => c.repositories.list(), ["repositories"]);
  // Each repository is downloaded to list its plugins, so this reloads only when the list changes
  // or after an action here, not on every server's status change.
  const plugins = resource(async (c) => {
    const urls = await c.repositories.list();
    const read = await Promise.all(
      urls.map(async (url) => {
        try {
          return { url, contents: await c.repositories.browse(url), error: "" };
        } catch (e) {
          return { url, contents: { skills: [], servers: [] }, error: describeError(e) };
        }
      }),
    );
    return { list: pluginsOf(read), errors: read.filter((r) => r.error) };
  }, ["repositories"]);

  let picked = $state<string | null>(null);
  let adding = $state(false);
  let installing = $state<Plugin | null>(null);
  let removing = $state<Plugin | null>(null);
  let busy = $state(false);
  const plugin = $derived(plugins.data?.list.find((p) => keyOf(p) === picked) ?? plugins.data?.list[0]);

  // The sidebar's + links here with ?add: open the dialog, then drop the parameter so a reload doesn't open it again.
  $effect(() => {
    if (!page.url.searchParams.has("add")) return;
    adding = true;
    void goto(resolve("/plugins"), { replaceState: true });
  });

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

  const update = (p: Plugin) =>
    act(() => (p.kind === "server" ? client.mcp.updateFromRepository(p.name) : client.skills.updateInstalled(p.name)), `Updated ${p.name}.`);
  const remove = (p: Plugin) =>
    act(() => (p.kind === "server" ? client.mcp.remove(p.name) : client.skills.delete(p.name)), `Removed ${p.name}.`);
  const forget = (url: string) => act(() => client.repositories.remove(url), `Removed ${shortRepository(url)} from the list.`);
</script>

<TopBar title="Plugins">
  {#snippet actions()}
    <button class="btn btn--primary" onclick={() => (adding = true)}><Plus size={16} /><span class="hide-narrow">Add a repository</span></button>
  {/snippet}
</TopBar>

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Plugins</h2>
        <p class="text-meta">MCP servers and skills from your repositories. Click one to see it on the right.</p>
      </div>
      <div class="tools">
        {#if plugins.data}<span class="pill">{plugins.data.list.length}</span>{/if}
        <button class="btn btn--ghost btn--sm" title="Download the repositories again" onclick={() => plugins.reload()}><RefreshCw size={14} /></button>
      </div>
    </header>
    <div class="scroll">
      {#if plugins.data === undefined}
        <p class="text-meta pad">{plugins.error ?? "Reading the repositories…"}</p>
      {:else}
        {#each plugins.data.errors as e (e.url)}<p class="error-text pad">{shortRepository(e.url)}: {e.error}</p>{/each}
        {#if plugins.data.list.length === 0}
          <EmptyState icon={Puzzle} title="No plugins" text="Add a repository with MCP servers or skills." />
        {:else}
          <table class="data-table">
            <thead><tr><th>Plugin</th><th class="hide-narrow">Kind</th><th class="hide-narrow">Repository</th><th>State</th></tr></thead>
            <tbody>
              {#each plugins.data.list as p (keyOf(p))}
                <tr class:selected={plugin && keyOf(p) === keyOf(plugin)} onclick={() => (picked = keyOf(p))}>
                  <td><button class="row-button" onclick={() => (picked = keyOf(p))}>{p.name}</button></td>
                  <td class="hide-narrow">{kindOf(p)}</td>
                  <td class="hide-narrow">{shortRepository(p.repository)}</td>
                  <td>
                    <span class="state"><span class="status-dot" style:--tone={p.installed ? "var(--color-success)" : undefined}></span>{p.installed ? "Installed" : "Not installed"}</span>
                  </td>
                </tr>
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
          <dt class="micro-label">Kind</dt>
          <dd>{kindOf(plugin)}</dd>
          <dt class="micro-label">Repository</dt>
          <dd>{shortRepository(plugin.repository)}</dd>
          {#if plugin.kind === "server"}
            <dt class="micro-label">Runs</dt>
            <dd>{plugin.server.transport === "stdio" ? "On this computer" : "Remotely"}</dd>
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
            <button class="btn btn--neutral btn--sm" disabled={busy} onclick={() => plugin && update(plugin)}><RefreshCw size={14} />Update</button>
            <button class="btn btn--danger btn--sm" disabled={busy} onclick={() => (removing = plugin ?? null)}><Trash2 size={14} />Remove</button>
          {:else}
            <button class="btn btn--primary btn--sm" disabled={busy} onclick={() => (installing = plugin ?? null)}><Download size={14} />Install</button>
          {/if}
        </div>
      </section>
    {/if}
    <section class="details surface--glass">
      <header><h3 class="micro-label">Repositories</h3></header>
      {#if repositories.data?.length === 0}<p class="text-meta">None. Add one with +.</p>{/if}
      <ul class="repos">
        {#each repositories.data ?? [] as url (url)}
          <li>
            <a href={url} target="_blank" rel="noreferrer">{shortRepository(url)}</a>
            <button class="btn btn--ghost btn--sm" title="Remove from the list (what's installed stays)" aria-label="Remove {shortRepository(url)}" onclick={() => forget(url)}><X size={14} /></button>
          </li>
        {/each}
      </ul>
    </section>
  </div>
</div>

{#if adding}
  <AddRepositoryDialog
    onclose={(added) => {
      adding = false;
      if (added) notices.notify(`Added ${shortRepository(added)}.`);
    }}
  />
{/if}

{#if installing}
  {@const p = installing}
  <InstallDialog
    repository={p.repository}
    picked={[p.name]}
    onclose={(installed) => {
      installing = null;
      if (installed) notices.notify(`Installed ${installed.join(", ")}. The assistant uses it from your next message.`);
      plugins.reload();
    }}
  />
{/if}

{#if removing}
  {@const p = removing}
  <Confirm
    title="Remove {p.name}?"
    text={p.kind === "server" ? "Its tools, skill and page go. Its data stays, for installing it again." : "The assistant won't be able to use this skill any more."}
    action="Remove"
    onanswer={(yes) => {
      removing = null;
      if (yes) void remove(p);
    }}
  />
{/if}

<style>
  .screen {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 16px;
    height: calc(100dvh - 76px);
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
  .repos {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .repos li {
    display: flex;
    align-items: center;
    justify-content: space-between;
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
