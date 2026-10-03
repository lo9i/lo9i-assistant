<script lang="ts">
  import type { McpServerSettings, McpToolInfo } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { parseArgs, parsePairs, selectionFor } from "$lib/mcp";
  import { describe } from "$lib/notices";
  import Modal from "../Modal.svelte";
  import ToolChecklist from "./ToolChecklist.svelte";

  let { onclose }: { onclose: (added?: string) => void } = $props();
  const { client } = useDaemon();

  let kind = $state<"stdio" | "http">("stdio");
  let name = $state("");
  let command = $state("");
  let args = $state("");
  let env = $state("");
  let url = $state("");
  let headers = $state("");
  let trusted = $state(false);
  let tools = $state<McpToolInfo[] | null>(null);
  let chosen = $state(new Set<string>());
  let busy = $state(false);
  let error = $state("");

  // The env values and headers are secrets: typed here, sent straight to the daemon, never shown again.
  function settings(): McpServerSettings {
    const local = kind === "stdio";
    return {
      name: name.trim(),
      command: local ? command.trim() : "",
      args: local ? parseArgs(args) : [],
      env: local ? parsePairs(env, "=") : {},
      url: local ? "" : url.trim(),
      headers: local ? {} : parsePairs(headers, ":"),
      trusted,
      include: [],
      exclude: [],
    };
  }

  async function run(action: () => Promise<void>): Promise<void> {
    busy = true;
    try {
      await action();
      error = "";
    } catch (e) {
      error = describe(e);
    } finally {
      busy = false;
    }
  }

  const look = () =>
    run(async () => {
      tools = await client.mcp.probe(settings());
      chosen = new Set(tools.map((t) => t.name));
    });

  const add = () =>
    run(async () => {
      await client.mcp.add({ ...settings(), ...selectionFor(tools ?? [], chosen) });
      onclose(name.trim());
    });

  // A change to the connection settings needs a new look at the tools.
  function edited(): void {
    tools = null;
  }
</script>

<Modal title="Add an MCP server" description="Its tools become available to the assistant from your next message." width={600} onclose={() => onclose()}>
  <div class="kinds" role="radiogroup" aria-label="Kind of server">
    <label><input type="radio" bind:group={kind} value="stdio" onchange={edited} /> Local command</label>
    <label><input type="radio" bind:group={kind} value="http" onchange={edited} /> Remote URL</label>
  </div>
  <label class="field">
    <span class="micro-label">Name</span>
    <input class="input" bind:value={name} placeholder="github" autocomplete="off" />
    <span class="text-caption">Lowercase letters, digits, - or _. Tools show up as mcp__name__tool.</span>
  </label>
  {#if kind === "stdio"}
    <label class="field">
      <span class="micro-label">Command</span>
      <input class="input" bind:value={command} oninput={edited} placeholder="npx" autocomplete="off" />
    </label>
    <label class="field">
      <span class="micro-label">Arguments</span>
      <textarea class="input" rows="2" bind:value={args} oninput={edited} placeholder="-y @modelcontextprotocol/server-filesystem /Users/me/notes"></textarea>
      <span class="text-caption">On one line separated by spaces, or one per line.</span>
    </label>
    <label class="field">
      <span class="micro-label">Environment (secret)</span>
      <textarea class="input secret" rows="2" bind:value={env} oninput={edited} placeholder="API_KEY=…" autocomplete="off" spellcheck="false"></textarea>
      <span class="text-caption">KEY=value, one per line. Stays in the daemon; only the names are shown later.</span>
    </label>
  {:else}
    <label class="field">
      <span class="micro-label">URL</span>
      <input class="input" bind:value={url} oninput={edited} placeholder="https://example.com/mcp" autocomplete="off" />
    </label>
    <label class="field">
      <span class="micro-label">Headers (secret)</span>
      <textarea class="input secret" rows="2" bind:value={headers} oninput={edited} placeholder="Authorization: Bearer …" autocomplete="off" spellcheck="false"></textarea>
      <span class="text-caption">Name: value, one per line. Stays in the daemon; only the names are shown later.</span>
    </label>
  {/if}
  <label class="check">
    <input type="checkbox" bind:checked={trusted} />
    <span>Trust this server <span class="text-caption">(otherwise every tool not marked read-only asks for approval)</span></span>
  </label>
  {#if tools}
    <div class="field">
      <span class="micro-label">Tools the assistant gets</span>
      <ToolChecklist {tools} {chosen} onchange={(c) => (chosen = c)} />
    </div>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onclose()}>Cancel</button>
    {#if tools}
      <button class="btn btn--primary" disabled={busy} onclick={add}>{busy ? "Adding…" : "Add"}</button>
    {:else}
      <button class="btn btn--primary" disabled={busy} onclick={look}>{busy ? "Connecting…" : "Look at tools"}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .kinds {
    display: flex;
    gap: 16px;
  }
  .kinds label,
  .check {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  textarea {
    resize: vertical;
    font-family: var(--font-mono);
  }
  /* Secrets are hidden like a password while not being edited. */
  .secret:not(:focus) {
    -webkit-text-security: disc;
  }
  p {
    margin: 0;
  }
</style>
