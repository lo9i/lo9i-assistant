<script lang="ts">
  import { keptKeys } from "$lib/keptKeys.svelte";
  import { untrack } from "svelte";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import Blocks from "@lucide/svelte/icons/blocks";
  import LogIn from "@lucide/svelte/icons/log-in";
  import Plus from "@lucide/svelte/icons/plus";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import Wrench from "@lucide/svelte/icons/wrench";
  import type { McpServerStatus } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { failures } from "$lib/health";
  import { STATUS_TONES, selectionFor, statusLabel, withTools } from "$lib/mcp";
  import { redirectUri } from "$lib/oauth";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import Toggle from "$lib/ui/Toggle.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import SettingsTabs from "$lib/ui/settings/SettingsTabs.svelte";
  import AddServerDialog from "$lib/ui/mcp/AddServerDialog.svelte";
  import SecretsDialog from "$lib/ui/mcp/SecretsDialog.svelte";
  import ToolChecklist from "$lib/ui/mcp/ToolChecklist.svelte";

  const { client, notices } = useDaemon();
  const servers = resource(async (c) => withTools(await c.mcp.servers()), ["mcp"]);
  // The Alerts page links here with ?s=<server name>.
  let picked = $state<string | null>(page.url.searchParams.get("s"));
  let adding = $state(false);
  let removing = $state(false);
  let secrets = $state<"env" | "headers" | null>(null);
  const server = $derived(servers.data?.find((s) => s.name === picked) ?? servers.data?.[0]);

  // The tool checklist starts from what the server has selected, and again only when that changes,
  // so a reload for another server's status doesn't undo unsaved checks.
  let chosen = $state(new Set<string>());
  const savedKey = $derived(
    `${server?.name}:${(server?.tools ?? [])
      .filter((t) => t.selected)
      .map((t) => t.name)
      .join(",")}`,
  );
  const saved = $derived(new Set(server?.tools.filter((t) => t.selected).map((t) => t.name)));
  $effect(() => {
    void savedKey;
    chosen = new Set(untrack(() => saved));
  });
  const dirty = $derived(chosen.size !== saved.size || [...chosen].some((n) => !saved.has(n)));

  function selected(s: McpServerStatus): string {
    return s.tools.length ? `${s.tools.filter((t) => t.selected).length} of ${s.tools.length}` : "–";
  }

  function change(action: () => Promise<unknown>): void {
    action().catch(notices.report);
  }

  function updateFromRepository(name: string): void {
    change(async () => {
      await client.mcp.updateFromRepository(name);
      notices.notify(`Updated ${name} from the extras.`);
    });
  }

  /** Opens the server's sign-in page; the /oauth page finishes it and the server connects here. */
  function signIn(name: string): void {
    change(async () => {
      window.open(await client.mcp.startSignIn(name, redirectUri()), "_blank", "noopener");
      notices.notify(`Finish signing in on the page that opened; ${name} connects here once it's done.`);
    });
  }

  function saveTools(s: McpServerStatus): void {
    change(async () => {
      await client.mcp.change(s.name, selectionFor(s.tools, chosen));
      notices.notify("Saved. The assistant gets these tools from your next message.");
    });
  }
</script>

<!-- A settings tab of its own page: the list and details need the full height. -->
<TopBar title="Settings">
  {#snippet actions()}
    <button class="btn btn--primary" onclick={() => (adding = true)}><Plus size={16} /><span class="hide-narrow">Add a server</span></button
    >
  {/snippet}
</TopBar>

<div class="tabs-bar"><SettingsTabs active="mcp" /></div>

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Servers</h2>
        <p class="text-meta">Tools the assistant gets from MCP servers. Click one to see it on the right.</p>
      </div>
      {#if servers.data}<span class="pill">{servers.data.length}</span>{/if}
    </header>
    <div class="scroll">
      {#if servers.error}
        <p class="error-text pad">{servers.error}</p>
      {:else if servers.data?.length === 0}
        <EmptyState icon={Blocks} title="No MCP servers" text="Add one to give the assistant its tools, like GitHub or a database." />
      {:else if servers.data && server}
        <table class="data-table">
          <thead
            ><tr
              ><th>Server</th><th class="hide-narrow">Kind</th><th class="hide-narrow">Added by</th><th class="hide-narrow">Tools</th><th
                >Status</th
              ></tr
            ></thead
          >
          <tbody>
            {#each servers.data as s (s.name)}
              <tr class:selected={s.name === server.name} onclick={() => (picked = s.name)}>
                <td><button class="row-button" onclick={() => (picked = s.name)}>{s.name}</button></td>
                <td class="hide-narrow">{s.transport === "stdio" ? "Local command" : "Remote URL"}</td>
                <td class="hide-narrow">{s.plugin ? `Plugin ${s.plugin}` : "You"}</td>
                <td class="hide-narrow">{selected(s)}</td>
                <td>
                  <span class="state"><span class="status-dot" style:--tone={STATUS_TONES[s.status]}></span>{statusLabel(s.status)}</span>
                  {#if s.failing}<span class="pill pill--danger">failing</span>{/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </section>

  <div class="column">
    {#if server}
      <section class="details surface--glass">
        <header>
          <h2 class="text-heading">{server.name}</h2>
          <Toggle
            checked={server.enabled}
            label={server.enabled ? "Turn off" : "Turn on"}
            onchange={(on) => change(() => client.mcp.change(server.name, { enabled: on }))}
          />
        </header>
        {#if server.error}<p class="error-text">{server.error}</p>{/if}
        <dl>
          <dt class="micro-label">Status</dt>
          <dd>{statusLabel(server.status)}</dd>
          {#if server.failures}<dt class="micro-label">Failures</dt>
            <dd>{failures(server)}</dd>{/if}
          {#if server.transport === "stdio"}
            <dt class="micro-label">Command</dt>
            <dd><code>{[server.command, ...server.args].join(" ")}</code></dd>
            <dt class="micro-label">Environment</dt>
            <dd>{server.env_keys.join(", ") || "none"}</dd>
          {:else}
            <dt class="micro-label">URL</dt>
            <dd><code>{server.url}</code></dd>
            <dt class="micro-label">Headers</dt>
            <dd>{server.header_keys.join(", ") || "none"}</dd>
          {/if}
          <dt class="micro-label">Added by</dt>
          <dd>{server.plugin ? `The ${server.plugin} plugin` : "You, by hand"}</dd>
          {#if server.source}
            <dt class="micro-label">Installed from</dt>
            <dd>{server.source}</dd>
          {/if}
          {#if server.channel}
            <dt class="micro-label">Channel</dt>
            <dd>Set it up in <a href={resolve("/plugins")}>Plugins</a></dd>
          {/if}
        </dl>
        <div class="trust">
          <div>
            <span>Trusted</span>
            <p class="text-caption">
              {server.trusted ? "Its tools run without asking." : "Every tool not marked read-only asks for approval first."}
            </p>
          </div>
          <Toggle
            checked={server.trusted}
            label={server.trusted ? "Stop trusting" : "Trust"}
            onchange={(on) => change(() => client.mcp.change(server.name, { trusted: on }))}
          />
        </div>
        <div class="actions">
          {#if server.status === "needs_sign_in"}
            <button class="btn btn--primary btn--sm" onclick={() => signIn(server.name)}><LogIn size={14} />Sign in</button>
          {/if}
          <button class="btn btn--neutral btn--sm" onclick={() => (secrets = server.transport === "stdio" ? "env" : "headers")}>
            {server.transport === "stdio" ? "Change environment" : "Change headers"}
          </button>
          {#if server.source}
            <button class="btn btn--neutral btn--sm" onclick={() => updateFromRepository(server.name)}><RefreshCw size={14} />Update</button
            >
          {/if}
          <!-- What a plugin installed goes with the plugin, in Settings → Plugins. -->
          {#if server.plugin}
            <span class="text-caption">To remove it, remove the {server.plugin} plugin in Settings → Plugins.</span>
          {:else}
            <button class="btn btn--danger btn--sm" onclick={() => (removing = true)}><Trash2 size={14} />Remove</button>
          {/if}
        </div>
      </section>
      <section class="tools-card surface--glass">
        <header>
          <h3 class="micro-label">Tools</h3>
          {#if dirty}<button class="btn btn--primary btn--sm" onclick={() => saveTools(server)}>Save</button>{/if}
        </header>
        <div class="tools-scroll">
          {#if server.status === "needs_sign_in"}
            <EmptyState icon={LogIn} title="Sign in" text="It asks you to sign in. Its tools show up here once you have." />
          {:else if server.tools.length === 0}
            <EmptyState icon={Wrench} title="Not connected" text="Its tools show up here once it connects." />
          {:else}
            <ToolChecklist tools={server.tools} {chosen} onchange={(c) => (chosen = c)} />
          {/if}
        </div>
      </section>
    {:else}
      <section class="tools-card surface--glass">
        <EmptyState icon={Blocks} title="No server selected" text="Pick one from the table to see it here." />
      </section>
    {/if}
  </div>
</div>

{#if adding}
  <AddServerDialog
    onclose={(added) => {
      adding = false;
      if (added) picked = added;
    }}
  />
{/if}

{#if secrets && server}
  <SecretsDialog server={server.name} kind={secrets} onclose={() => (secrets = null)} />
{/if}

{#if removing && server}
  <Confirm
    title="Remove {server.name}?"
    text="The assistant loses its tools from your next message, and its settings are deleted."
    action="Remove"
    onanswer={(yes) => {
      removing = false;
      if (yes) change(async () => keptKeys.ask(await client.mcp.remove(server.name)));
    }}
  />
{/if}

<style>
  .tabs-bar {
    max-width: 1600px;
    margin: 0 auto;
    padding: 0 16px;
  }
  .screen {
    display: flex;
    /* Cards take the height of their content, up to the screen below the tabs; long lists scroll inside. */
    align-items: flex-start;
    gap: 16px;
    padding: 16px;
    height: calc(100dvh - 76px - 34px);
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
    align-self: stretch;
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
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
  }
  .details header,
  .trust,
  .tools-card header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
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
    flex-wrap: wrap;
  }
  .tools-card {
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
  .tools-card header {
    padding: 16px 16px 0;
    min-height: 32px;
  }
  h3 {
    margin: 0;
  }
  .tools-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
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
    .tools-card {
      min-height: 240px;
    }
  }
</style>
