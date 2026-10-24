<script lang="ts">
  import RotateCcw from "@lucide/svelte/icons/rotate-ccw";
  import type { PromptSection } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import { canSave, draftOf, promptState } from "$lib/prompts";
  import Confirm from "../Confirm.svelte";
  import SettingsCard from "../Card.svelte";

  // The texts the assistant's system prompt starts with (core/conversation/prompt_edits.py). An edit is used
  // from the next message in each conversation, which starts a new epoch for it with nothing summarized.
  const { client, notices } = useDaemon();
  const loaded = resource((c) => c.prompts.list(), ["prompts"]);
  let picked = $state("persona");
  // What the user typed and hasn't saved, by section.
  let drafts = $state<Record<string, string>>({});
  let confirming = $state(false);
  let error = $state("");

  const section = $derived(loaded.data?.find((s) => s.name === picked) ?? loaded.data?.[0]);
  const draft = $derived(section ? draftOf(section, drafts) : "");
  const textState = $derived(section ? promptState(section, draft) : "built-in");

  function settle(saved: PromptSection): void {
    loaded.data = loaded.data?.map((s) => (s.name === saved.name ? saved : s));
    delete drafts[saved.name];
    error = "";
  }

  async function save(name: string, text: string): Promise<void> {
    try {
      settle(await client.prompts.save(name, text));
      notices.notify("Saved. It applies from your next message in each conversation.");
    } catch (e) {
      error = describe(e);
    }
  }

  async function keep(name: string): Promise<void> {
    try {
      settle(await client.prompts.keep(name));
      notices.notify("Your edit stays as it is.");
    } catch (e) {
      error = describe(e);
    }
  }

  async function reset(name: string): Promise<void> {
    try {
      settle(await client.prompts.reset(name));
      notices.notify("Back to the built-in text, from your next message.");
    } catch (e) {
      error = describe(e);
    }
  }
</script>

<SettingsCard
  id="prompt"
  title="System prompt"
  sub="The instructions the assistant's system prompt starts with. Memory, skills and accounts follow them. An edit applies from your next message in each conversation."
>
  {#snippet status()}
    {#if section}
      {#if textState === "unsaved"}<span class="pill pill--warn">Unsaved changes</span>
      {:else if textState === "edited"}<span class="pill pill--accent">Edited</span>
      {:else}<span class="pill">Built-in</span>{/if}
    {/if}
  {/snippet}
  {#if loaded.data === undefined || section === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else}
    <div class="tabs" role="radiogroup" aria-label="Section">
      {#each loaded.data as s (s.name)}
        <button
          role="radio"
          aria-checked={s.name === section.name}
          class:active={s.name === section.name}
          onclick={() => ((picked = s.name), (error = ""))}
        >
          {s.title}{#if s.edited || drafts[s.name] !== undefined}<span class="dot" aria-label="changed"></span>{/if}
        </button>
      {/each}
    </div>
    <p class="text-meta">{section.description}</p>
    {#if section.problem}
      <p class="error-text">{section.problem} The assistant uses the built-in text below until you reset or save it.</p>
    {/if}
    {#if section.built_in_changes}
      <!-- An update changed the built-in text this edit hides: what changed, to take into the edit or not. -->
      <div class="notice-warn changes">
        <p class="text-label">The built-in text changed since you edited it. Your edit is still what the assistant uses.</p>
        <pre>{section.built_in_changes}</pre>
        <p class="text-meta">Take what you want into your edit and save it, keep your edit as it is, or reset to the new built-in text.</p>
        <div class="actions">
          <button class="btn btn--neutral btn--sm" onclick={() => keep(section.name)}>Keep my edit</button>
        </div>
      </div>
    {/if}
    <textarea
      class="input"
      rows="18"
      spellcheck="false"
      aria-label={section.title}
      value={draft}
      oninput={(e) => (drafts[section.name] = e.currentTarget.value)}></textarea>
    {#if error}<p class="error-text">{error}</p>{/if}
    <div class="actions">
      <button class="btn btn--primary btn--sm" disabled={!canSave(section, draft)} onclick={() => save(section.name, draft)}>Save</button>
      {#if textState === "unsaved"}
        <button class="btn btn--ghost btn--sm" onclick={() => delete drafts[section.name]}>Discard changes</button>
      {/if}
      {#if section.edited}
        <button class="btn btn--neutral btn--sm" onclick={() => (confirming = true)}><RotateCcw size={14} />Reset to default</button>
      {/if}
    </div>
  {/if}
</SettingsCard>

{#if confirming && section}
  {@const name = section.name}
  <Confirm
    title="Reset {section.title}?"
    text="Your edit is deleted and the assistant uses the built-in text again."
    action="Reset"
    onanswer={(yes) => {
      confirming = false;
      if (yes) void reset(name);
    }}
  />
{/if}

<style>
  .tabs {
    align-self: flex-start;
  }
  .dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-left: 6px;
    border-radius: var(--radius-full);
    background: var(--color-action-primary);
    vertical-align: middle;
  }
  textarea {
    width: 100%;
    min-height: 240px;
    resize: vertical;
    font-family: var(--font-mono);
    font-size: var(--font-size-sm);
    line-height: 1.5;
  }
  .changes {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .changes pre {
    margin: 0;
    max-height: 240px;
    overflow: auto;
    font-family: var(--font-mono);
    font-size: var(--font-size-sm);
    white-space: pre-wrap;
  }
  .actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  p {
    margin: 0;
  }
</style>
