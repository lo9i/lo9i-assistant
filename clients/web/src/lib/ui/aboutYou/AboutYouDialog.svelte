<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import { untrack } from "svelte";
  import type { AboutYou, FoundServer, FoundSkill, HelpTopic, Suggested } from "$lib/api/types";
  import { HELP_TOPICS, savedAnswers, startAnswers } from "$lib/aboutYou.svelte";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t, type Key } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { hasSetup } from "$lib/plugins";
  import Modal from "../Modal.svelte";
  import PluginIcon from "../PluginIcon.svelte";
  import PluginSetupModal from "../chat/PluginSetupModal.svelte";
  import InstallDialog from "../repositories/InstallDialog.svelte";

  // The About you step (core/memory/about_you.py): the user's name, how to reply and what they mainly want help
  // with, saved to the profile at once. Then the extras' plugins for what they picked, each installed only when they
  // press Install, with the same install and setup as Plugins. Closing it before saving leaves the profile as it was.
  let { onclose }: { onclose: () => void } = $props();
  const { client } = useDaemon();

  const TOPICS: Record<HelpTopic, Key> = {
    email: "aboutYou.topics.email",
    calendar: "aboutYou.topics.calendar",
    coding: "aboutYou.topics.coding",
    expenses: "aboutYou.topics.expenses",
    media: "aboutYou.topics.media",
    hosts: "aboutYou.topics.hosts",
  };
  const LENGTHS: { value: AboutYou["reply_length"]; label: Key }[] = [
    { value: "short", label: "aboutYou.short" },
    { value: "detailed", label: "aboutYou.detailed" },
    { value: null, label: "aboutYou.noPreference" },
  ];

  let form = $state<AboutYou>(startAnswers(null));
  let busy = $state(false);
  let error = $state("");
  let suggestions = $state<Suggested[] | null>(null);
  let installing = $state<{ server?: FoundServer; skill?: FoundSkill } | null>(null);
  let settingUp = $state<FoundServer | null>(null);
  let installed = $state(new Set<string>());

  untrack(() => void load());

  async function load(): Promise<void> {
    try {
      form = startAnswers(await client.memory.aboutYou());
    } catch (e) {
      error = describe(e);
    }
  }

  async function save(): Promise<void> {
    const answers = savedAnswers(form);
    if (!answers.name) {
      error = t("aboutYou.needsName");
      return;
    }
    busy = true;
    try {
      const found = await client.memory.saveAboutYou(answers);
      error = "";
      if (found.length) suggestions = found;
      else onclose();
    } catch (e) {
      error = describe(e);
    } finally {
      busy = false;
    }
  }

  function toggle(topic: HelpTopic, on: boolean): void {
    const picked = form.help_with ?? [];
    form.help_with = on ? [...picked, topic] : picked.filter((p) => p !== topic);
  }

  /** A plugin with a setup (an email account, signing in) goes on to it, as one the agent offers does. */
  function closedInstall(names?: string[]): void {
    const server = installing?.server;
    installing = null;
    if (!names?.length) return;
    installed = new Set([...installed, ...names]);
    if (server && hasSetup(server)) settingUp = server;
  }
</script>

{#snippet plugin(found: FoundServer | FoundSkill, install: () => void)}
  <li class="plugin">
    <PluginIcon icon={found.icon} />
    <div class="what">
      <code>{found.name}</code>
      <p class="text-caption">{found.description}</p>
    </div>
    {#if installed.has(found.name)}
      <span class="pill pill--accent"><Check size={12} />{t("aboutYou.installed")}</span>
    {:else}
      <button class="btn btn--neutral btn--sm" onclick={install}>{t("aboutYou.install")}</button>
    {/if}
  </li>
{/snippet}

{#if settingUp}
  <PluginSetupModal server={settingUp} ondone={() => (settingUp = null)} />
{:else if installing}
  <InstallDialog server={installing.server} skill={installing.skill} onclose={closedInstall} />
{:else if suggestions}
  <Modal title={t("aboutYou.pluginsTitle")} description={t("aboutYou.pluginsDescription")} width={600} {onclose}>
    {#each suggestions as group (group.topic)}
      <section class="group">
        <h3 class="micro-label">{t(TOPICS[group.topic])}</h3>
        {#if group.topic === "email"}<p class="text-caption flush">{t("aboutYou.emailHint")}</p>{/if}
        <ul>
          {#each group.servers as server (server.name)}
            {@render plugin(server, () => (installing = { server }))}
          {/each}
          {#each group.skills as skill (skill.name)}
            {@render plugin(skill, () => (installing = { skill }))}
          {/each}
        </ul>
      </section>
    {/each}
    {#snippet footer()}
      <button class="btn btn--primary" onclick={onclose}>{t("aboutYou.done")}</button>
    {/snippet}
  </Modal>
{:else}
  <Modal title={t("aboutYou.title")} description={t("aboutYou.description")} width={560} {onclose}>
    <form
      class="form"
      id="about-you"
      onsubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <div class="row">
        <label class="field">
          <span class="field-label">{t("aboutYou.name")}<span class="required"> *</span></span>
          <!-- svelte-ignore a11y_autofocus -->
          <input class="input" bind:value={form.name} autocomplete="given-name" maxlength="200" autofocus />
        </label>
        <label class="field">
          <span class="field-label">{t("aboutYou.language")}</span>
          <input class="input" bind:value={form.language} placeholder={t("aboutYou.languageHint")} maxlength="100" />
        </label>
      </div>
      <div class="row">
        <label class="field">
          <span class="field-label">{t("aboutYou.email")}</span>
          <input class="input" type="email" bind:value={form.email} autocomplete="email" maxlength="320" title={t("aboutYou.emailUse")} />
        </label>
        <label class="field">
          <span class="field-label">{t("aboutYou.replyLength")}</span>
          <select
            class="input"
            value={LENGTHS.findIndex((l) => l.value === form.reply_length)}
            onchange={(e) => (form.reply_length = LENGTHS[Number(e.currentTarget.value)].value)}
          >
            {#each LENGTHS as length, i (length.label)}
              <option value={i}>{t(length.label)}</option>
            {/each}
          </select>
        </label>
      </div>
      <fieldset class="field">
        <legend class="field-label">{t("aboutYou.helpWith")}</legend>
        <div class="chips">
          {#each HELP_TOPICS as topic (topic)}
            <label class="chip"
              ><input type="checkbox" checked={form.help_with?.includes(topic)} onchange={(e) => toggle(topic, e.currentTarget.checked)} />
              {t(TOPICS[topic])}</label
            >
          {/each}
        </div>
        <input class="input" bind:value={form.other_help} placeholder={t("aboutYou.otherHelp")} maxlength="500" />
      </fieldset>
    </form>
    {#if error}<p class="error-text">{error}</p>{/if}
    {#snippet footer()}
      <button class="btn btn--ghost" onclick={onclose}>{t("aboutYou.later")}</button>
      <button class="btn btn--primary" type="submit" form="about-you" disabled={busy}>{t("aboutYou.save")}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .form {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    border: none;
    margin: 0;
    padding: 0;
  }
  .field-label {
    font-weight: 600;
    padding: 0;
    margin-bottom: 0;
  }
  .required {
    color: var(--color-danger);
  }
  .row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  @media (max-width: 520px) {
    .row {
      grid-template-columns: 1fr;
    }
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 4px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    padding: 4px 12px;
    border: 1px solid var(--color-border);
    border-radius: 999px;
    font-size: var(--font-size-sm);
    cursor: pointer;
    user-select: none;
  }
  .chip input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .chip:has(input:checked) {
    border-color: var(--color-accent);
    background: color-mix(in srgb, var(--color-accent) 18%, transparent);
  }
  .chip:has(input:focus-visible) {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }
  .group + .group {
    margin-top: 12px;
  }
  .group h3 {
    margin: 0 0 6px;
  }
  .flush {
    margin: 0 0 6px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .plugin {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .what {
    flex: 1;
    min-width: 0;
  }
  .what p {
    margin: 2px 0 0;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
</style>
