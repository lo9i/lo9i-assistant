<script lang="ts">
  import Pin from "@lucide/svelte/icons/pin";
  import X from "@lucide/svelte/icons/x";
  import { t } from "$lib/i18n.svelte";

  // The skills pinned to this conversation, each with a button to unpin it. Nothing when none is pinned.
  let { skills, onunpin }: { skills: string[]; onunpin: (name: string) => void } = $props();
</script>

{#if skills.length}
  <div class="pinned" aria-label={t("chat.pinnedSkills")}>
    <Pin size={14} aria-hidden="true" />
    {#each skills as skill (skill)}
      <span class="pill pill--accent">
        {skill}
        <button type="button" class="unpin" aria-label={t("chat.unpin", { skill })} onclick={() => onunpin(skill)}>
          <X size={12} />
        </button>
      </span>
    {/each}
  </div>
{/if}

<style>
  .pinned {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    padding: 4px 16px;
    color: var(--color-text-muted);
  }
  .unpin {
    display: inline-grid;
    place-items: center;
    padding: 0;
    border: none;
    background: none;
    color: inherit;
    cursor: pointer;
  }
</style>
