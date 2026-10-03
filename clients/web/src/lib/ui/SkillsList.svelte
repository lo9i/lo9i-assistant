<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import Wand from "@lucide/svelte/icons/wand-sparkles";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { markdown } from "$lib/markdown";
  import { describe } from "$lib/notices";
  import Confirm from "./Confirm.svelte";
  import EmptyState from "./EmptyState.svelte";
  import SettingsCard from "./Card.svelte";

  const { client, notices } = useDaemon();
  const skills = resource((c) => c.skills.list(), ["skills"]);
  let open = $state<string | null>(null);
  const skill = resource((c) => (open ? c.skills.get(open) : Promise.resolve(null)), ["skills"]);
  let confirming = $state<string | null>(null);
  // The skill being edited, and the form's text.
  let editing = $state<string | null>(null);
  let description = $state("");
  let instructions = $state("");
  let error = $state("");

  function startEditing(): void {
    if (!skill.data) return;
    editing = skill.data.name;
    description = skill.data.description;
    instructions = skill.data.instructions;
    error = "";
  }

  async function save(): Promise<void> {
    if (!editing) return;
    try {
      await client.skills.update(editing, description, instructions);
      editing = null;
      notices.notify("Saved. The assistant uses it from now on.");
    } catch (e) {
      error = describe(e);
    }
  }
</script>

<SettingsCard id="skills" title="Saved skills" sub="Reusable instructions the assistant saved. It picks one when a task matches.">
  {#snippet status()}
    {#if skills.data}<span class="pill">{skills.data.length}</span>{/if}
  {/snippet}
  {#if skills.data === undefined}
    <p class="text-meta">{skills.error ?? "Loading…"}</p>
  {:else if skills.data.length === 0}
    <EmptyState icon={Wand} title="No skills yet" text="Ask the assistant to save how to do something as a skill." />
  {:else}
    <div class="list">
      {#each skills.data as s (s.name)}
        <div class="skill">
          <button
            class="head"
            aria-expanded={open === s.name}
            onclick={() => ((open = open === s.name ? null : s.name), (editing = null))}
          >
            <span class="tile"><Wand size={16} /></span>
            <span class="text">
              <strong>{s.name}</strong>
              <span class="text-meta">{s.description}</span>
            </span>
            <span class="chevron" class:turned={open === s.name}><ChevronRight size={18} /></span>
          </button>
          {#if open === s.name && skill.data?.name === s.name}
            <div class="body">
              {#if editing === s.name}
                <label class="field">
                  <span class="micro-label">Description</span>
                  <input class="input" bind:value={description} placeholder="When to use it, in one line" />
                </label>
                <label class="field">
                  <span class="micro-label">Instructions</span>
                  <textarea class="input" rows="12" bind:value={instructions}></textarea>
                </label>
                {#if error}<p class="error-text">{error}</p>{/if}
                <div class="actions">
                  <button class="btn btn--primary btn--sm" disabled={!description.trim() || !instructions.trim()} onclick={save}
                    >Save</button
                  >
                  <button class="btn btn--ghost btn--sm" onclick={() => (editing = null)}>Cancel</button>
                </div>
              {:else}
                <div class="prose">{@html markdown(skill.data.instructions)}</div>
                <div class="actions">
                  <button class="btn btn--neutral btn--sm" onclick={startEditing}><Pencil size={14} />Edit</button>
                  <button class="btn btn--danger btn--sm" onclick={() => (confirming = s.name)}><Trash2 size={14} />Delete</button>
                </div>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</SettingsCard>

{#if confirming}
  <Confirm
    title="Delete {confirming}?"
    text="The assistant won't be able to use this skill any more."
    action="Delete"
    onanswer={(yes) => {
      if (yes && confirming) client.skills.delete(confirming).catch(notices.report);
      confirming = null;
    }}
  />
{/if}

<style>
  .list {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }
  .skill + .skill {
    border-top: 1px solid var(--color-border);
  }
  .head {
    display: grid;
    grid-template-columns: 36px 1fr 20px;
    align-items: center;
    gap: 10px;
    width: 100%;
    min-height: 56px;
    padding: 10px 16px;
    border: 0;
    background: none;
    text-align: left;
    cursor: pointer;
    transition: background 0.12s ease;
  }
  .head:hover {
    background: color-mix(in srgb, var(--color-text-primary) 4%, transparent);
  }
  .tile {
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-text-primary) 8%, transparent);
    color: var(--color-text-muted);
  }
  .text {
    display: flex;
    flex-direction: column;
  }
  .chevron {
    color: var(--color-text-faint);
    transition: transform 0.12s ease;
  }
  .turned {
    transform: rotate(90deg);
  }
  .body {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    padding: 0 16px 16px 62px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-self: stretch;
  }
  textarea {
    resize: vertical;
    font-family: var(--font-mono, monospace);
  }
  .actions {
    display: flex;
    gap: 8px;
  }
</style>
