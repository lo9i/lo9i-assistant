<script lang="ts">
  import { page } from "$app/state";
  import AppearanceCard from "$lib/ui/settings/AppearanceCard.svelte";
  import EmailCard from "$lib/ui/settings/EmailCard.svelte";
  import MicrophoneCard from "$lib/ui/settings/MicrophoneCard.svelte";
  import ModelCard from "$lib/ui/settings/ModelCard.svelte";
  import NameCard from "$lib/ui/settings/NameCard.svelte";
  import SlackCard from "$lib/ui/settings/SlackCard.svelte";
  import SpeechCard from "$lib/ui/settings/SpeechCard.svelte";
  import SpokenRepliesCard from "$lib/ui/settings/SpokenRepliesCard.svelte";
  import StartupCard from "$lib/ui/settings/StartupCard.svelte";
  import TelegramCard from "$lib/ui/settings/TelegramCard.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const TABS = [
    { id: "general", label: "General" },
    { id: "integrations", label: "Integrations" },
    { id: "audio", label: "Audio" },
  ];
  const tab = $derived(TABS.find((t) => t.id === page.url.searchParams.get("tab"))?.id ?? "general");
</script>

<TopBar title="Settings" />

<div class="shell">
  <nav class="tabs" aria-label="Settings">
    {#each TABS as t (t.id)}
      <a href="?tab={t.id}" class:active={t.id === tab} aria-current={t.id === tab ? "page" : undefined}>{t.label}</a>
    {/each}
  </nav>
  {#if tab === "general"}
    <div class="grid">
      <div class="wide"><ModelCard /></div>
      <NameCard />
      <AppearanceCard />
      <div class="wide"><StartupCard /></div>
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
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    align-items: start;
  }
  .wide {
    grid-column: 1 / -1;
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
