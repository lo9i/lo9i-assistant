<script lang="ts">
  import type { FoundServer, RepositoryContents } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import Modal from "../Modal.svelte";

  let { onclose }: { onclose: (installed?: string[]) => void } = $props();
  const { client } = useDaemon();

  let url = $state("");
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

  const look = () =>
    run(async () => {
      const contents = await client.repositories.browse(url.trim());
      const onlyOne = contents.skills.length + contents.servers.length === 1;
      skills = new Set(onlyOne ? contents.skills.map((s) => s.name) : []);
      servers = new Set(onlyOne ? contents.servers.map((s) => s.name) : []);
      values = Object.fromEntries(contents.servers.map((s) => [s.name, Object.fromEntries(s.fields.map((f) => [f.key, ""]))]));
      found = contents;
    });

  const install = () =>
    run(async () => {
      const chosen = [...servers].map((name) => ({ name, values: values[name] }));
      await client.repositories.install(url.trim(), [...skills], chosen);
      onclose([...skills, ...servers]);
    });

  function toggled(set: Set<string>, name: string, on: boolean): Set<string> {
    const next = new Set(set);
    if (on) next.add(name);
    else next.delete(name);
    return next;
  }

  function kind(s: FoundServer): string {
    const parts = [s.transport === "stdio" ? "local" : "remote"];
    if (s.skill) parts.push("with its skill");
    if (s.page) parts.push("with a web page");
    return parts.join(", ");
  }
</script>

<Modal
  title="Install from a repository"
  description="Skills and MCP servers from a git repository. What you install runs on the computer running the assistant, so install only from people you trust."
  width={600}
  onclose={() => onclose()}
>
  <label class="field">
    <span class="micro-label">Repository</span>
    <input class="input" bind:value={url} oninput={() => (found = null)} placeholder="https://github.com/user/extras" autocomplete="off" />
  </label>
  {#if found}
    <ul>
      {#each found.skills as skill (skill.name)}
        <li>
          <label>
            <input type="checkbox" checked={skills.has(skill.name)} onchange={(e) => (skills = toggled(skills, skill.name, e.currentTarget.checked))} />
            <span class="pill">skill</span><code>{skill.name}</code>
          </label>
          <p class="text-caption">{skill.description}</p>
          {#if skill.files.length}<p class="text-caption">Files: {skill.files.join(", ")}</p>{/if}
        </li>
      {/each}
      {#each found.servers as server (server.name)}
        <li>
          <label>
            <input type="checkbox" checked={servers.has(server.name)} onchange={(e) => (servers = toggled(servers, server.name, e.currentTarget.checked))} />
            <span class="pill">MCP server, {kind(server)}</span><code>{server.name}</code>
          </label>
          <p class="text-caption">{server.description}</p>
          {#if servers.has(server.name)}
            {#each server.fields as f (f.key)}
              <label class="field indented">
                <span class="micro-label">{f.label}{f.secret ? " (secret)" : ""}</span>
                <input class="input" type={f.secret ? "password" : "text"} bind:value={values[server.name][f.key]} autocomplete="off" />
                {#if f.help}<a class="text-caption" href={f.help} target="_blank" rel="noreferrer">{f.help}</a>{/if}
              </label>
            {/each}
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onclose()}>Cancel</button>
    {#if found}
      <button class="btn btn--primary" disabled={busy || skills.size + servers.size === 0} onclick={install}>{busy ? "Installing…" : "Install"}</button>
    {:else}
      <button class="btn btn--primary" disabled={busy || !url.trim()} onclick={look}>{busy ? "Downloading…" : "Look"}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
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
  li > label {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }
  p {
    margin: 0;
    padding-left: 22px;
  }
  .error-text {
    padding-left: 0;
  }
</style>
