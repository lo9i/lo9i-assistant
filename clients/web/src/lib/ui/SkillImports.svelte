<script lang="ts">
  import Download from "@lucide/svelte/icons/download";
  import Wand from "@lucide/svelte/icons/wand-sparkles";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { outcomeLine, pickedByDefault, selectable, stateLabel, whereFrom } from "$lib/skillImports";
  import EmptyState from "./EmptyState.svelte";
  import SettingsCard from "./Card.svelte";
  import Toggle from "./Toggle.svelte";

  const { client, notices } = useDaemon();
  const found = resource((c) => c.skills.importable(), ["skills"]);
  let picked = $state<string[]>([]);
  let replace = $state(false);
  let importing = $state(false);
  let results = $state<string[]>([]);

  const items = $derived(found.data?.skills ?? []);
  const toImport = $derived(items.filter(selectable));

  function toggle(id: string, on: boolean): void {
    picked = on ? [...picked, id] : picked.filter((p) => p !== id);
  }

  async function importPicked(): Promise<void> {
    importing = true;
    try {
      const outcomes = await client.skills.importSkills(picked, replace);
      results = outcomes.map(outcomeLine);
      picked = [];
      const done = outcomes.filter((o) => o.action !== "failed").length;
      if (done) notices.notify(`Imported ${done} skill${done === 1 ? "" : "s"}. The assistant uses them from now on.`);
    } catch (e) {
      notices.report(e);
    } finally {
      importing = false;
    }
  }
</script>

<!-- /import-skills opens this card (#import). Nothing is imported until the user picks it. -->
<SettingsCard
  id="import"
  title="Skills from other agents"
  sub="Claude Code's and Codex's skills on this computer, and in the projects you handed to an agent. Pick the ones to copy into the assistant's skills."
>
  {#snippet status()}
    {#if toImport.length}<span class="pill">{toImport.length}</span>{/if}
  {/snippet}
  {#if found.data === undefined}
    <p class="text-meta">{found.error ?? "Looking…"}</p>
  {:else if items.length === 0}
    <EmptyState
      icon={Wand}
      title="None found"
      text="Claude Code keeps skills in ~/.claude/skills and a project's .claude/skills; Codex in ~/.codex/skills, ~/.agents/skills and ~/.codex/prompts."
    />
  {:else}
    <div class="list">
      {#each items as item (item.id)}
        <label class="item" class:off={!selectable(item)} title={item.id}>
          <input
            type="checkbox"
            disabled={!selectable(item)}
            checked={picked.includes(item.id)}
            onchange={(e) => toggle(item.id, e.currentTarget.checked)}
          />
          <span class="text">
            <strong
              >{item.name}
              <span class="pill">{whereFrom(item)}</span>
              {#if item.state === "changed"}<span class="pill pill--warn">{stateLabel(item)}</span>
              {:else if item.state === "imported"}<span class="pill pill--accent">{stateLabel(item)}</span>{/if}
              {#if item.needs_agent?.length}<span class="pill pill--warn" title={item.needs_agent.join(" ")}
                  >works best handed to a coding agent</span
                >{/if}</strong
            >
            <span class="text-meta">{item.description}</span>
            {#if item.state === "new" && item.renamed}<span class="text-caption">Will be {item.renamed}.</span>{/if}
            {#each item.problems ?? [] as problem (problem)}<span class="error-text">{problem}</span>{/each}
          </span>
        </label>
      {/each}
    </div>
    <div class="actions">
      <button class="btn btn--primary btn--sm" disabled={!picked.length || importing} onclick={importPicked}
        ><Download size={14} />{picked.length ? `Import ${picked.length}` : "Import"}</button
      >
      <button class="btn btn--ghost btn--sm" onclick={() => (picked = items.filter(pickedByDefault).map((i) => i.id))}>Pick new</button>
      <span class="replace">
        <Toggle checked={replace} label="Replace skills with the same name" onchange={(on) => (replace = on)} />
        <span class="text-meta">Replace a skill of yours with the same name instead of adding the agent's name</span>
      </span>
    </div>
    {#each results as line, i (i)}<p class="text-caption">{line}</p>{/each}
  {/if}
  {#if found.data?.suggestions.length}
    <p class="text-caption">
      Not imported: {found.data.suggestions.join(", ")}. They're instructions for a coding agent; ask the assistant to read one and save
      what's useful as a skill.
    </p>
  {/if}
</SettingsCard>

<style>
  .list {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }
  .item {
    display: grid;
    grid-template-columns: 20px 1fr;
    align-items: start;
    gap: 10px;
    padding: 12px 16px;
    cursor: pointer;
  }
  .item + .item {
    border-top: 1px solid var(--color-border);
  }
  .item.off {
    cursor: default;
  }
  .item input {
    margin-top: 3px;
  }
  .text {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .replace {
    display: flex;
    align-items: center;
    gap: 8px;
  }
</style>
