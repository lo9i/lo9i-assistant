<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  const { client } = useDaemon();
  const current = resource((c) => c.identity.name(), ["settings"]);
  let name = $state("");
  let message = $state("");

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

<SettingsCard id="assistant" title="Assistant" sub="What it calls itself.">
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
