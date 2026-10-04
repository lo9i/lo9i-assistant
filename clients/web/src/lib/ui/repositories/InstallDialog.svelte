<script lang="ts">
  import SecretInput from "../SecretInput.svelte";
  import { untrack } from "svelte";
  import type { FoundServer, FoundSkill, RepositoryContents } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import { missingField, optional } from "$lib/plugins";
  import Modal from "../Modal.svelte";

  // `kind`: only MCP servers (the MCP servers page) or only skills (the Skills page). `server` or
  // `skill`: just this plugin, already read from the extras (the Plugins page, or one the agent offers
  // in the chat). What's installed already isn't offered.
  type Props = {
    onclose: (installed?: string[]) => void;
    kind?: "server" | "skill";
    server?: FoundServer;
    skill?: FoundSkill;
  };
  let { onclose, kind: shownKind, server: onlyServer, skill: onlySkill }: Props = $props();
  const only = $derived(onlyServer ?? onlySkill);
  const { client } = useDaemon();

  let found = $state<RepositoryContents | null>(null);
  let skills = $state(new Set<string>());
  let servers = $state(new Set<string>());
  // Values typed for each server's fields, by server name and field key. Secret ones go straight to the daemon.
  let values = $state<Record<string, Record<string, string>>>({});
  let busy = $state(false);
  let error = $state("");

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

  function offer(contents: RepositoryContents): void {
    const onlyOne = contents.skills.length + contents.servers.length === 1;
    skills = new Set(onlyOne ? contents.skills.map((s) => s.name) : []);
    servers = new Set(onlyOne ? contents.servers.map((s) => s.name) : []);
    values = Object.fromEntries(contents.servers.map((s) => [s.name, Object.fromEntries(s.fields.map((f) => [f.key, ""]))]));
    found = contents;
  }

  const look = () =>
    run(async () => {
      const all = await client.repositories.browse();
      const offered = (k: "server" | "skill", p: { name: string; installed?: boolean }) => !p.installed && (!shownKind || shownKind === k);
      // The MCP servers page lists servers with tools: a plugin without them is installed from Plugins.
      const listed = (s: FoundServer) => !(shownKind === "server" && s.transport === "none");
      offer({
        skills: all.skills.filter((s) => offered("skill", s)),
        servers: all.servers.filter((s) => offered("server", s) && listed(s)),
      });
    });

  /** "telegram needs Bot token." for the first chosen server with a required value left empty. */
  function missing(): string {
    for (const s of found?.servers ?? []) {
      const label = servers.has(s.name) ? missingField(s, values[s.name]) : null;
      if (label) return `${s.name} needs ${label}.`;
    }
    return "";
  }

  const install = () => {
    error = missing();
    if (error) return;
    return run(async () => {
      const chosen = [...servers].map((name) => ({ name, values: values[name] }));
      await client.repositories.install([...skills], chosen);
      onclose([...skills, ...servers]);
    });
  };

  // A plugin given already is offered before the first render, which reads its values; otherwise
  // what the extras offer, as soon as it opens.
  // The dialog is opened for one plugin and closed after; it never changes to another.
  untrack(() => only && offer({ skills: onlySkill ? [onlySkill] : [], servers: onlyServer ? [onlyServer] : [] }));
  $effect(() => {
    if (!only) void untrack(look);
  });

  function toggled(set: Set<string>, name: string, on: boolean): Set<string> {
    const next = new Set(set);
    if (on) next.add(name);
    else next.delete(name);
    return next;
  }

  function kind(s: FoundServer): string {
    if (s.transport === "none") return s.email ? "Email provider" : "Channel";
    const parts = [s.transport === "http" ? "remote" : "local"];
    if (s.channel) parts.push("a chat channel");
    if (s.skill) parts.push("with its skill");
    if (s.page) parts.push("with a web page");
    return `MCP server, ${parts.join(", ")}`;
  }

  /** "t.me/BotFather" for a help link: the address without its scheme reads better. */
  function shortLink(url: string): string {
    return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
  }
</script>

{#snippet fields(server: FoundServer)}
  {#if server.steps?.length}
    <ol class="steps">
      {#each server.steps as step, i (i)}<li class="text-label">{step}</li>{/each}
    </ol>
  {/if}
  {#each server.fields as f (f.key)}
    <label class="field">
      <span class="field-label">{f.label}</span>
      {#if f.secret}
        <SecretInput
          label={f.label}
          bind:value={values[server.name][f.key]}
          required={!optional(server, f.key)}
          placeholder={optional(server, f.key) ? "Leave empty to keep the one already saved" : ""}
        />
      {:else}
        <input
          class="input"
          bind:value={values[server.name][f.key]}
          required={!optional(server, f.key)}
          placeholder={optional(server, f.key) ? "Leave empty to keep the one already saved" : ""}
          autocomplete="off"
        />
      {/if}
      {#if f.help}<span class="text-caption">Get it at <a href={f.help} target="_blank" rel="noreferrer">{shortLink(f.help)}</a></span>{/if}
    </label>
  {/each}
{/snippet}

<Modal
  title={only ? `Install ${only.name}` : "Install a plugin"}
  description={only
    ? only.description
    : "MCP servers, chat channels and skills from the assistant's extras. What you install runs on the computer running the assistant."}
  width={600}
  onclose={() => onclose()}
>
  {#if onlyServer}
    <div class="form">{@render fields(onlyServer)}</div>
  {:else if onlySkill}
    {#if onlySkill.files.length}<p class="text-caption flush">Files: {onlySkill.files.join(", ")}</p>{/if}
  {:else if found === null && !error}<p class="text-meta">Looking at the extras…</p>
  {:else if found && found.skills.length + found.servers.length === 0}
    <p class="text-meta">
      Everything the extras offer{shownKind === "server" ? " as MCP servers" : shownKind === "skill" ? " as skills" : ""} is installed already.
    </p>
  {:else if found}
    <ul>
      {#each found.skills as skill (skill.name)}
        <li>
          <label>
            <input
              type="checkbox"
              checked={skills.has(skill.name)}
              onchange={(e) => (skills = toggled(skills, skill.name, e.currentTarget.checked))}
            />
            <span class="pill">skill</span><code>{skill.name}</code>
          </label>
          <p class="text-caption">{skill.description}</p>
          {#if skill.files.length}<p class="text-caption">Files: {skill.files.join(", ")}</p>{/if}
        </li>
      {/each}
      {#each found.servers as server (server.name)}
        <li>
          <label>
            <input
              type="checkbox"
              checked={servers.has(server.name)}
              onchange={(e) => (servers = toggled(servers, server.name, e.currentTarget.checked))}
            />
            <span class="pill">{kind(server)}</span><code>{server.name}</code>
          </label>
          <p class="text-caption">{server.description}</p>
          {#if servers.has(server.name)}
            <div class="form indented">{@render fields(server)}</div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onclose()}>Cancel</button>
    {#if found}
      <button class="btn btn--primary" disabled={busy || skills.size + servers.size === 0} onclick={install}
        >{busy ? "Installing…" : "Install"}</button
      >
    {:else if error}
      <button class="btn btn--primary" disabled={busy} onclick={look}>Try again</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .form {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .steps {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 0;
    padding-left: 20px;
  }
  .field {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
  }
  .field-label {
    font-weight: 600;
  }
  .indented {
    padding: 8px 0 0 22px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  li > label:not(.field) {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }
  p {
    margin: 0;
    padding-left: 22px;
  }
  .error-text,
  .flush {
    padding-left: 0;
  }
</style>
