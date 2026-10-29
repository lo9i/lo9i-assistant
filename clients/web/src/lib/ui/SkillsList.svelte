<script lang="ts">
  import { keptKeys } from "$lib/keptKeys.svelte";
  import { page } from "$app/state";
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import Pencil from "@lucide/svelte/icons/pencil";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import Wand from "@lucide/svelte/icons/wand-sparkles";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { markdown } from "$lib/markdown";
  import { failures } from "$lib/health";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import Confirm from "./Confirm.svelte";
  import EmptyState from "./EmptyState.svelte";
  import SettingsCard from "./Card.svelte";

  const { client, notices } = useDaemon();
  const skills = resource((c) => c.skills.list(), ["skills"]);
  // The Alerts page links here with ?s=<skill name>.
  let open = $state<string | null>(page.url.searchParams.get("s"));
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

  async function updateInstalled(name: string): Promise<void> {
    try {
      await client.skills.updateInstalled(name);
      notices.notify(t("skills.updated", { name }));
    } catch (e) {
      notices.report(e);
    }
  }

  async function save(): Promise<void> {
    if (!editing) return;
    try {
      await client.skills.update(editing, description, instructions);
      editing = null;
      notices.notify(t("skills.saved"));
    } catch (e) {
      error = describe(e);
    }
  }
</script>

<SettingsCard id="skills" title={t("skills.title")} sub={t("skills.sub")}>
  {#snippet status()}
    {#if skills.data}<span class="pill">{skills.data.length}</span>{/if}
  {/snippet}
  {#if skills.data === undefined}
    <p class="text-meta">{skills.error ?? t("common.loading")}</p>
  {:else if skills.data.length === 0}
    <EmptyState icon={Wand} title={t("skills.none")} text={t("skills.noneHint")} />
  {:else}
    <div class="list">
      {#each skills.data as s (s.name)}
        <div class="skill">
          <button class="head" aria-expanded={open === s.name} onclick={() => ((open = open === s.name ? null : s.name), (editing = null))}>
            <span class="tile"><Wand size={16} /></span>
            <span class="text">
              <strong
                >{s.name}
                {#if s.problems?.length}<span class="pill pill--warn">{t("skills.hasProblems")}</span>
                {:else if s.failing}<span class="pill pill--danger">{t("skills.failing")}</span>{/if}
                {#if s.plugin}<span class="pill" title={t("skills.addedByPlugin")}>{t("skills.pluginTag", { plugin: s.plugin })}</span
                  >{/if}</strong
              >
              <span class="text-meta">{s.description}</span>
            </span>
            <span class="chevron" class:turned={open === s.name}><ChevronRight size={18} /></span>
          </button>
          {#if open === s.name && skill.data?.name === s.name}
            <div class="body">
              {#if editing === s.name}
                <label class="field">
                  <span class="micro-label">{t("skills.description")}</span>
                  <input class="input" bind:value={description} placeholder={t("skills.descriptionPlaceholder")} />
                </label>
                <label class="field">
                  <span class="micro-label">{t("skills.instructions")}</span>
                  <textarea class="input" rows="12" bind:value={instructions}></textarea>
                </label>
                {#if error}<p class="error-text">{error}</p>{/if}
                <div class="actions">
                  <button class="btn btn--primary btn--sm" disabled={!description.trim() || !instructions.trim()} onclick={save}
                    >{t("common.save")}</button
                  >
                  <button class="btn btn--ghost btn--sm" onclick={() => (editing = null)}>{t("common.cancel")}</button>
                </div>
              {:else}
                {@const files = skill.data.files ?? []}
                {#each skill.data.problems ?? [] as problem (problem)}<p class="error-text">{problem}</p>{/each}
                {#if s.failures}<p class="error-text">{failures(s)}</p>{/if}
                <div class="prose">{@html markdown(skill.data.instructions)}</div>
                <dl>
                  <dt class="micro-label">{t("skills.addedBy")}</dt>
                  <dd>{skill.data.plugin ? t("skills.thePlugin", { plugin: skill.data.plugin }) : t("skills.youOrAssistant")}</dd>
                  {#if files.length}<dt class="micro-label">{t("skills.files")}</dt>
                    <dd>{files.join(", ")}</dd>{/if}
                  {#if skill.data.server}
                    <dt class="micro-label">{t("skills.comesWith")}</dt>
                    <dd>{t("skills.comesWithServer", { server: skill.data.server })}</dd>
                  {:else if skill.data.source}<dt class="micro-label">{t("skills.installedFrom")}</dt>
                    <dd>{skill.data.source}</dd>{/if}
                </dl>
                <div class="actions">
                  <button class="btn btn--neutral btn--sm" onclick={startEditing}><Pencil size={14} />{t("common.edit")}</button>
                  {#if skill.data.source && !skill.data.server}
                    <button class="btn btn--neutral btn--sm" onclick={() => updateInstalled(s.name)}
                      ><RefreshCw size={14} />{t("common.update")}</button
                    >
                  {/if}
                  <!-- What a plugin installed goes with the plugin, in Settings → Plugins. -->
                  {#if skill.data.plugin}
                    <span class="text-caption">{t("skills.deleteWithPlugin", { plugin: skill.data.plugin })}</span>
                  {:else}
                    <button class="btn btn--danger btn--sm" onclick={() => (confirming = s.name)}
                      ><Trash2 size={14} />{t("common.delete")}</button
                    >
                  {/if}
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
    title={t("skills.deleteTitle", { name: confirming })}
    text={t("skills.deleteText")}
    action={t("common.delete")}
    onanswer={(yes) => {
      if (yes && confirming) client.skills.delete(confirming).then((kept) => keptKeys.ask(kept), notices.report);
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
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 12px;
    margin: 0;
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
</style>
