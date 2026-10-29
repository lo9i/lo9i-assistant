<script lang="ts">
  import type { McpServerSettings, McpToolInfo } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { parseArgs, parsePairs, selectionFor } from "$lib/mcp";
  import { t } from "$lib/i18n.svelte";
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
  // The server asks to sign in: it's added without a look at its tools, then signed in to.
  let signIn = $state(false);
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
      const probe = await client.mcp.probe(settings());
      tools = probe.tools;
      signIn = probe.sign_in;
      chosen = new Set(tools.map((tool) => tool.name));
    });

  const add = () =>
    run(async () => {
      await client.mcp.add({ ...settings(), ...selectionFor(tools ?? [], chosen) });
      onclose(name.trim());
    });

  // A change to the connection settings needs a new look at the tools.
  function edited(): void {
    tools = null;
    signIn = false;
  }
</script>

<Modal title={t("mcpAdd.title")} description={t("mcpAdd.description")} width={600} onclose={() => onclose()}>
  <div class="kinds" role="radiogroup" aria-label={t("mcpAdd.kind")}>
    <label><input type="radio" bind:group={kind} value="stdio" onchange={edited} /> {t("mcpAdd.local")}</label>
    <label><input type="radio" bind:group={kind} value="http" onchange={edited} /> {t("mcpAdd.remote")}</label>
  </div>
  <label class="field">
    <span class="micro-label">{t("mcpAdd.name")}</span>
    <input class="input" bind:value={name} placeholder="github" autocomplete="off" />
    <span class="text-caption">{t("mcpAdd.nameHint")}</span>
  </label>
  {#if kind === "stdio"}
    <label class="field">
      <span class="micro-label">{t("mcpAdd.command")}</span>
      <input class="input" bind:value={command} oninput={edited} placeholder="npx" autocomplete="off" />
    </label>
    <label class="field">
      <span class="micro-label">{t("mcpAdd.arguments")}</span>
      <textarea
        class="input"
        rows="2"
        bind:value={args}
        oninput={edited}
        placeholder="-y @modelcontextprotocol/server-filesystem /Users/me/notes"></textarea>
      <span class="text-caption">{t("mcpAdd.argumentsHint")}</span>
    </label>
    <label class="field">
      <span class="micro-label">{t("mcpAdd.environment")}</span>
      <textarea
        class="input secret"
        rows="2"
        bind:value={env}
        oninput={edited}
        placeholder="API_KEY=…"
        autocomplete="off"
        spellcheck="false"></textarea>
      <span class="text-caption">{t("mcpAdd.environmentHint")}</span>
    </label>
  {:else}
    <label class="field">
      <span class="micro-label">URL</span>
      <input class="input" bind:value={url} oninput={edited} placeholder="https://example.com/mcp" autocomplete="off" />
    </label>
    <label class="field">
      <span class="micro-label">{t("mcpAdd.headers")}</span>
      <textarea
        class="input secret"
        rows="2"
        bind:value={headers}
        oninput={edited}
        placeholder="Authorization: Bearer …"
        autocomplete="off"
        spellcheck="false"></textarea>
      <span class="text-caption">{t("mcpAdd.headersHint")}</span>
    </label>
  {/if}
  <label class="check">
    <input type="checkbox" bind:checked={trusted} />
    <span>{t("mcpAdd.trust")} <span class="text-caption">{t("mcpAdd.trustHint")}</span></span>
  </label>
  {#if signIn}
    <p class="text-caption">{t("mcpAdd.signIn")}</p>
  {:else if tools}
    <div class="field">
      <span class="micro-label">{t("mcpAdd.tools")}</span>
      <ToolChecklist {tools} {chosen} onchange={(c) => (chosen = c)} />
    </div>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onclose()}>{t("common.cancel")}</button>
    {#if tools}
      <button class="btn btn--primary" disabled={busy} onclick={add}>{busy ? t("mcpAdd.adding") : t("repositories.add")}</button>
    {:else}
      <button class="btn btn--primary" disabled={busy} onclick={look}>{busy ? t("mcpAdd.connecting") : t("mcpAdd.look")}</button>
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
