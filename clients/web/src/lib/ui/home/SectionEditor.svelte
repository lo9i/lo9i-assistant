<script lang="ts">
  import type { HomeSection } from "$lib/api/types";
  import { MAX_COLUMNS } from "$lib/home";
  import Modal from "../Modal.svelte";

  type Props = {
    // null for a new section.
    section: HomeSection | null;
    // The installed plugins with tools, to pick from.
    plugins: string[];
    // Why the last save was refused.
    error: string;
    onsave: (section: HomeSection) => void;
    onclose: () => void;
  };
  let { section, plugins, error, onsave, onclose }: Props = $props();

  // svelte-ignore state_referenced_locally
  let title = $state(section?.title ?? "");
  // svelte-ignore state_referenced_locally
  let prompt = $state(section?.prompt ?? "");
  // svelte-ignore state_referenced_locally
  let picked = $state<string[]>([...(section?.plugins ?? [])]);
  // svelte-ignore state_referenced_locally
  let columns = $state(section?.columns ?? 0);
  const widths = Array.from({ length: MAX_COLUMNS }, (_, i) => i + 1);
  // A plugin the section names that isn't installed stays listed, so saving doesn't drop it unseen.
  const choices = $derived([...new Set([...plugins, ...picked])].sort());

  function toggle(name: string, on: boolean): void {
    picked = on ? [...picked, name] : picked.filter((p) => p !== name);
  }

  function save(): void {
    onsave({ id: section?.id ?? "", title, prompt, plugins: picked, columns });
  }
</script>

<Modal
  title={section ? `Edit ${section.title}` : "New section"}
  description="The assistant reads your plugins with what this says and shows what it finds as a list."
  width={600}
  {onclose}
>
  <label class="field">
    <span class="micro-label">Title</span>
    <input class="input" bind:value={title} placeholder="Calendar" />
  </label>
  <label class="field">
    <span class="micro-label">What to show</span>
    <textarea class="input" rows="7" bind:value={prompt} placeholder="Today's events from all my calendars, by start time."></textarea>
  </label>
  <fieldset class="field">
    <legend class="micro-label">Plugins it reads</legend>
    {#if choices.length === 0}
      <p class="text-meta">No plugin with tools is installed yet. Install one in Plugins.</p>
    {:else}
      <div class="plugins">
        {#each choices as name (name)}
          <label class="plugin">
            <input type="checkbox" checked={picked.includes(name)} onchange={(e) => toggle(name, e.currentTarget.checked)} />
            {name}
            {#if !plugins.includes(name)}<span class="text-caption">not installed</span>{/if}
          </label>
        {/each}
      </div>
      <p class="text-meta">None picked: it may read every plugin. It only uses tools that read, never ones that change things.</p>
    {/if}
  </fieldset>
  <label class="field">
    <span class="micro-label">Width</span>
    <select class="input" bind:value={columns}>
      <option value={0}>Automatic: two columns when it has more than it shows at once</option>
      {#each widths as n (n)}
        <option value={n}>{n === 1 ? "1 column" : `${n} columns`}</option>
      {/each}
    </select>
    <span class="text-caption">On a narrower screen it takes as many as there are. Dragging the card's right edge sets it too.</span>
  </label>
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost btn--sm" onclick={onclose}>Cancel</button>
    <button class="btn btn--primary btn--sm" disabled={!title.trim() || !prompt.trim()} onclick={save}>Save</button>
  {/snippet}
</Modal>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 0;
    padding: 0;
    border: 0;
  }
  textarea {
    resize: vertical;
  }
  .plugins {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
  }
  .plugin {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--font-size-sm);
  }
  .text-meta {
    margin: 0;
  }
</style>
