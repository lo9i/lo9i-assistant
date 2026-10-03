<script lang="ts">
  import type { FoundSkill } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import Modal from "../Modal.svelte";

  let { onclose }: { onclose: (installed?: string[]) => void } = $props();
  const { client } = useDaemon();

  let url = $state("");
  let found = $state<FoundSkill[] | null>(null);
  let chosen = $state(new Set<string>());
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
      found = await client.skills.browse(url.trim());
      chosen = new Set(found.length === 1 ? [found[0].name] : []);
    });

  const install = () =>
    run(async () => {
      const names = [...chosen];
      await client.skills.install(url.trim(), names);
      onclose(names);
    });

  function toggle(name: string, on: boolean): void {
    const next = new Set(chosen);
    if (on) next.add(name);
    else next.delete(name);
    chosen = next;
  }
</script>

<Modal
  title="Install skills"
  description="From a git repository. Their scripts run on the computer running the assistant, so install only from people you trust."
  width={600}
  onclose={() => onclose()}
>
  <label class="field">
    <span class="micro-label">Repository</span>
    <input class="input" bind:value={url} oninput={() => (found = null)} placeholder="https://github.com/user/skills" autocomplete="off" />
  </label>
  {#if found}
    <ul>
      {#each found as skill (skill.name)}
        <li>
          <label>
            <input type="checkbox" checked={chosen.has(skill.name)} onchange={(e) => toggle(skill.name, e.currentTarget.checked)} />
            <code>{skill.name}</code>
          </label>
          <p class="text-caption">{skill.description}</p>
          {#if skill.files.length}<p class="text-caption">Files: {skill.files.join(", ")}</p>{/if}
        </li>
      {/each}
    </ul>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onclose()}>Cancel</button>
    {#if found}
      <button class="btn btn--primary" disabled={busy || chosen.size === 0} onclick={install}>{busy ? "Installing…" : "Install"}</button>
    {:else}
      <button class="btn btn--primary" disabled={busy || !url.trim()} onclick={look}>{busy ? "Downloading…" : "Look at skills"}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  label {
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
