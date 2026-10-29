<script lang="ts">
  import type { McpToolInfo } from "$lib/api/types";
  import { t } from "$lib/i18n.svelte";

  type Props = { tools: McpToolInfo[]; chosen: Set<string>; onchange: (chosen: Set<string>) => void };
  let { tools, chosen, onchange }: Props = $props();

  function toggle(name: string, on: boolean): void {
    const next = new Set(chosen);
    if (on) next.add(name);
    else next.delete(name);
    onchange(next);
  }
</script>

{#if tools.length === 0}
  <p class="text-meta">{t("mcpAdd.noTools")}</p>
{:else}
  <div class="all">
    <button class="btn btn--ghost btn--sm" type="button" onclick={() => onchange(new Set(tools.map((tool) => tool.name)))}
      >{t("mcpAdd.all")}</button
    >
    <button class="btn btn--ghost btn--sm" type="button" onclick={() => onchange(new Set())}>{t("mcpAdd.none")}</button>
  </div>
  <ul>
    {#each tools as tool (tool.name)}
      <li>
        <label>
          <input type="checkbox" checked={chosen.has(tool.name)} onchange={(e) => toggle(tool.name, e.currentTarget.checked)} />
          <span class="name">
            <code>{tool.name}</code>
            {#if tool.read_only}<span class="pill">{t("mcpAdd.readOnly")}</span>{/if}
          </span>
        </label>
        {#if tool.description}<p class="text-caption">{tool.description}</p>{/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .all {
    display: flex;
    gap: 4px;
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
    gap: 8px;
    cursor: pointer;
  }
  .name {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  p {
    margin: 2px 0 0 24px;
    overflow-wrap: anywhere;
  }
</style>
