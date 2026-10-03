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

<SettingsCard title="Name" sub="What the assistant calls itself. The Telegram bot's display name follows it.">
  <form class="row" onsubmit={save}>
    <input class="input" bind:value={name} placeholder="Name" aria-label="Name" />
    <button class="btn btn--primary" type="submit" disabled={!name.trim() || name.trim() === current.data}>Save</button>
  </form>
  {#if message}<p class="text-meta">{message}</p>{/if}
</SettingsCard>

<style>
  .row {
    display: flex;
    gap: 8px;
  }
  p {
    margin: -12px 0 0;
  }
</style>
