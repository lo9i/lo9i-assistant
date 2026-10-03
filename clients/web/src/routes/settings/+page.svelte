<script lang="ts">
  import { page } from "$app/state";
  import AssistantCard from "$lib/ui/settings/AssistantCard.svelte";
  import EmailCard from "$lib/ui/settings/EmailCard.svelte";
  import GetToKnowYouCard from "$lib/ui/settings/GetToKnowYouCard.svelte";
  import MicrophoneCard from "$lib/ui/settings/MicrophoneCard.svelte";
  import ModelCard from "$lib/ui/settings/ModelCard.svelte";
  import PluginUpdatesCard from "$lib/ui/settings/PluginUpdatesCard.svelte";
  import SlackCard from "$lib/ui/settings/SlackCard.svelte";
  import SpeechCard from "$lib/ui/settings/SpeechCard.svelte";
  import SpokenRepliesCard from "$lib/ui/settings/SpokenRepliesCard.svelte";
  import StartupCard from "$lib/ui/settings/StartupCard.svelte";
  import TelegramCard from "$lib/ui/settings/TelegramCard.svelte";
  import WebSearchCard from "$lib/ui/settings/WebSearchCard.svelte";
  import SettingsTabs from "$lib/ui/settings/SettingsTabs.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import { theme, type ThemePreference } from "$lib/theme.svelte";

  const TABS = ["general", "integrations", "audio"];
  const THEMES: Array<[ThemePreference, string]> = [
    ["dark", "Dark"],
    ["light", "Light"],
    ["system", "System"],
  ];
  const tab = $derived(TABS.find((t) => t === page.url.searchParams.get("tab")) ?? "general");
</script>

<TopBar title="Settings" />

<div class="shell">
  <div class="bar">
    <SettingsTabs active={tab} />
    <!-- Kept in this browser. -->
    <div class="tabs" role="radiogroup" aria-label="Theme" title="Theme, kept in this browser">
      {#each THEMES as [value, label] (value)}
        <button
          role="radio"
          aria-checked={theme.preference === value}
          class:active={theme.preference === value}
          onclick={() => theme.set(value)}
        >
          {label}
        </button>
      {/each}
    </div>
  </div>
  {#if tab === "general"}
    <!-- The model on one side; the small settings stacked on the other. -->
    <div class="grid">
      <div class="stack">
        <ModelCard />
      </div>
      <div class="stack">
        <AssistantCard />
        <GetToKnowYouCard />
        <StartupCard />
        <PluginUpdatesCard />
      </div>
    </div>
  {:else if tab === "audio"}
    <div class="grid">
      <div class="stack">
        <SpeechCard />
      </div>
      <div class="stack">
        <SpokenRepliesCard />
        <MicrophoneCard />
      </div>
    </div>
  {:else}
    <!-- Two independent stacks, so a tall card doesn't leave a gap beside it. -->
    <div class="grid">
      <div class="stack">
        <TelegramCard />
        <EmailCard />
      </div>
      <div class="stack">
        <SlackCard />
        <WebSearchCard />
      </div>
    </div>
  {/if}
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    gap: 24px;
    padding: 16px 16px 40px;
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
