<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import { theme, type ThemePreference } from "$lib/theme.svelte";
  import SettingsCard from "../Card.svelte";

  const { client } = useDaemon();
  const current = resource((c) => c.identity.name(), ["settings"]);
  let name = $state("");
  let message = $state("");

  const THEMES: Array<[ThemePreference, string]> = [
    ["dark", "Dark"],
    ["light", "Light"],
    ["system", "System"],
  ];

  $effect(() => {
    name = current.data ?? "";
  });

  async function save(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    try {
      message = `Saved: ${await client.identity.rename(name)}. It applies from the next message.`;
    } catch (err) {
      message = describe(err);
    }
  }
</script>

<!-- Small settings that are one choice each: the assistant's name, and this browser's theme. -->
<SettingsCard id="assistant" title="Assistant" sub="Its name, and how this browser shows the app.">
  <form class="setting" onsubmit={save}>
    <div class="label">
      <span class="text-label">Name</span>
      <span class="text-caption">The Telegram bot's display name follows it.</span>
    </div>
    <div class="control">
      <input class="input" bind:value={name} placeholder="Name" aria-label="Name" />
      <button class="btn btn--primary btn--sm" type="submit" disabled={!name.trim() || name.trim() === current.data}>Save</button>
    </div>
  </form>
  {#if message}<p class="text-meta">{message}</p>{/if}
  <div class="setting">
    <div class="label">
      <span class="text-label">Theme</span>
      <span class="text-caption">Kept in this browser.</span>
    </div>
    <div class="tabs" role="radiogroup" aria-label="Theme">
      {#each THEMES as [value, label] (value)}
        <button role="radio" aria-checked={theme.preference === value} class:active={theme.preference === value} onclick={() => theme.set(value)}>
          {label}
        </button>
      {/each}
    </div>
  </div>
</SettingsCard>

<style>
  .setting {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }
  .label {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .control {
    display: flex;
    gap: 8px;
  }
  .control .input {
    width: 200px;
  }
  p {
    margin: -12px 0 0;
  }
</style>
