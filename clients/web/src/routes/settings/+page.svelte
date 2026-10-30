<script lang="ts">
  import { page } from "$app/state";
  import AgentDoneCard from "$lib/ui/settings/AgentDoneCard.svelte";
  import AssistantCard from "$lib/ui/settings/AssistantCard.svelte";
  import EmailCard from "$lib/ui/settings/EmailCard.svelte";
  import FolderPanelCard from "$lib/ui/settings/FolderPanelCard.svelte";
  import LanguageCard from "$lib/ui/settings/LanguageCard.svelte";
  import HostCard from "$lib/ui/settings/HostCard.svelte";
  import KeptKeysCard from "$lib/ui/settings/KeptKeysCard.svelte";
  import MicrophoneCard from "$lib/ui/settings/MicrophoneCard.svelte";
  import DispatchCard from "$lib/ui/settings/DispatchCard.svelte";
  import ModelCard from "$lib/ui/settings/ModelCard.svelte";
  import PromptCard from "$lib/ui/settings/PromptCard.svelte";
  import SpeechCard from "$lib/ui/settings/SpeechCard.svelte";
  import SpokenRepliesCard from "$lib/ui/settings/SpokenRepliesCard.svelte";
  import StartupCard from "$lib/ui/settings/StartupCard.svelte";
  import WebSearchCard from "$lib/ui/settings/WebSearchCard.svelte";
  import SettingsTabs from "$lib/ui/settings/SettingsTabs.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import { t, type Key } from "$lib/i18n.svelte";
  import { theme, type ThemePreference } from "$lib/theme.svelte";

  const TABS = ["general", "model", "prompt", "audio", "system"];
  const THEMES: Array<[ThemePreference, Key]> = [
    ["dark", "settings.dark"],
    ["light", "settings.light"],
    ["system", "settings.system"],
  ];
  const tab = $derived(TABS.find((t) => t === page.url.searchParams.get("tab")) ?? "general");
</script>

<TopBar title={t("nav.settings")} />

<div class="shell">
  <div class="bar">
    <SettingsTabs active={tab} />
    <!-- Kept in this browser. -->
    <div class="tabs" role="radiogroup" aria-label={t("settings.theme")} title={t("settings.themeHint")}>
      {#each THEMES as [value, label] (value)}
        <button
          role="radio"
          aria-checked={theme.preference === value}
          class:active={theme.preference === value}
          onclick={() => theme.set(value)}
        >
          {t(label)}
        </button>
      {/each}
    </div>
  </div>
  {#if tab === "general"}
    <!-- Two balanced columns: assistant, language, agent notices and the folder panel; startup, search, email. -->
    <div class="grid">
      <div class="stack">
        <AssistantCard />
        <LanguageCard />
        <AgentDoneCard />
        <FolderPanelCard />
      </div>
      <div class="stack">
        <StartupCard />
        <WebSearchCard />
        <EmailCard />
      </div>
    </div>
  {:else if tab === "model"}
    <div class="grid">
      <div class="stack">
        <ModelCard />
        <DispatchCard />
      </div>
    </div>
  {:else if tab === "prompt"}
    <!-- The whole width: the editor needs room. -->
    <PromptCard />
  {:else if tab === "system"}
    <div class="grid">
      <div class="stack">
        <HostCard />
      </div>
      <div class="stack">
        <KeptKeysCard />
      </div>
    </div>
  {:else}
    <div class="grid">
      <div class="stack">
        <SpeechCard />
      </div>
      <div class="stack">
        <SpokenRepliesCard />
        <MicrophoneCard />
      </div>
    </div>
  {/if}
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    gap: 24px;
    padding: 0 16px 40px;
    max-width: 1600px;
    margin: 0 auto;
  }
  .bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    align-items: start;
  }
  .stack {
    display: flex;
    flex-direction: column;
    gap: 24px;
    min-width: 0;
  }
  @media (max-width: 1100px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
