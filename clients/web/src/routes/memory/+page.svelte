<script lang="ts">
  import UserRound from "@lucide/svelte/icons/user-round";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import { startGetToKnowYou } from "$lib/chat/getToKnowYou";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { sectionLabel } from "$lib/memory";
  import Card from "$lib/ui/Card.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import SettingsTabs from "$lib/ui/settings/SettingsTabs.svelte";

  // Read only: the assistant keeps this up to date from conversations, and changes it when asked in chat.
  const memory = resource((c) => c.memory.snapshot(), ["memory"]);
  const { chat } = useDaemon();
  const sections = $derived(Object.entries(memory.data?.profile ?? {}));
</script>

<!-- A settings tab of its own page. -->
<TopBar title="Settings" />

<div class="shell">
  <SettingsTabs active="memory" />
  {#if memory.error}
    <p class="error-text">{memory.error}</p>
  {:else if memory.data}
    <Card title="Profile" sub="Always in the assistant's mind. Changes apply from the next conversation.">
      {#snippet status()}
        <button class="btn btn--neutral btn--sm" onclick={() => startGetToKnowYou(chat)}><Sparkles size={14} />Get to know me</button>
      {/snippet}
      {#if sections.length === 0}
        <EmptyState icon={UserRound} title="Nothing yet" text="The profile fills in as you talk." />
      {:else}
        <dl>
          {#each sections as [name, items] (name)}
            <div class="section">
              <dt class="micro-label">{sectionLabel(name)}</dt>
              <dd>
                <ul>
                  {#each items as item, i (i)}<li>{item}</li>{/each}
                </ul>
              </dd>
            </div>
          {/each}
        </dl>
      {/if}
    </Card>
  {/if}
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 16px 16px 40px;
    max-width: 1600px;
    margin: 0 auto;
  }
  dl {
    display: flex;
    flex-direction: column;
    gap: 20px;
    margin: 0;
  }
  .section {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  dd {
    margin: 0;
  }
  ul {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 0;
    padding-left: 18px;
    overflow-wrap: anywhere;
  }
</style>
