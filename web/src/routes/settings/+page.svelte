<script lang="ts">
  import { page } from "$app/state";
  import AppearanceCard from "$lib/ui/settings/AppearanceCard.svelte";
  import DevicesCard from "$lib/ui/settings/DevicesCard.svelte";
  import EmailCard from "$lib/ui/settings/EmailCard.svelte";
  import NameCard from "$lib/ui/settings/NameCard.svelte";
  import StartupCard from "$lib/ui/settings/StartupCard.svelte";
  import TelegramCard from "$lib/ui/settings/TelegramCard.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const TABS = [
    { id: "general", label: "General" },
    { id: "integrations", label: "Integrations" },
    { id: "devices", label: "Devices" },
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
      <NameCard />
      <AppearanceCard />
      <div class="wide"><StartupCard /></div>
    </div>
  {:else if tab === "integrations"}
    <div class="grid">
      <TelegramCard />
      <EmailCard />
    </div>
  {:else}
    <DevicesCard />
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
  @media (max-width: 1100px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
