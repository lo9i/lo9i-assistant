<script lang="ts">
  import { theme, type ThemePreference } from "$lib/theme.svelte";
  import SettingsCard from "../Card.svelte";

  const OPTIONS: Array<[ThemePreference, string]> = [
    ["dark", "Dark"],
    ["light", "Light"],
    ["system", "System"],
  ];
</script>

<SettingsCard title="Appearance" sub="Kept in this browser.">
  <div class="tabs" role="radiogroup" aria-label="Theme">
    {#each OPTIONS as [value, label] (value)}
      <button role="radio" aria-checked={theme.preference === value} class:active={theme.preference === value} onclick={() => theme.set(value)}>
        {label}
      </button>
    {/each}
  </div>
</SettingsCard>
