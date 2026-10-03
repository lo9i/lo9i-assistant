<script lang="ts">
  import BookOpen from "@lucide/svelte/icons/book-open";
  import Lightbulb from "@lucide/svelte/icons/lightbulb";
  import UserRound from "@lucide/svelte/icons/user-round";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import { startGetToKnowYou } from "$lib/chat/getToKnowYou";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { sectionLabel } from "$lib/memory";
  import Card from "$lib/ui/Card.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  // Read only: the assistant keeps this up to date from conversations, and changes it when asked in chat.
  const memory = resource((c) => c.memory.snapshot(), ["memory"]);
  const { chat } = useDaemon();
  const sections = $derived(Object.entries(memory.data?.profile ?? {}));
  const facts = $derived(memory.data?.facts ?? []);
  const episodes = $derived(memory.data?.episodes ?? []);
</script>

<TopBar title="About you" />

<div class="shell">
  {#if memory.error}
    <p class="error-text">{memory.error}</p>
  {:else if memory.data}
    <div class="grid">
      <div class="stack">
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
      </div>
      <div class="stack">
        <Card title="Facts" sub="Details the assistant remembers.">
          {#snippet status()}<span class="pill">{facts.length}</span>{/snippet}
          {#if facts.length === 0}
            <EmptyState icon={Lightbulb} title="No facts yet" text="Facts are saved as they come up." />
          {:else}
            <ul class="list">
              {#each facts as fact, i (i)}<li>{fact}</li>{/each}
            </ul>
          {/if}
        </Card>
        <Card title="Recent conversations" sub="Summaries of past conversations.">
          {#snippet status()}<span class="pill">{episodes.length}</span>{/snippet}
          {#if episodes.length === 0}
            <EmptyState icon={BookOpen} title="None yet" text="Conversations are summarized after you leave them." />
          {:else}
            <ul class="list">
              {#each episodes as episode, i (i)}<li>{episode}</li>{/each}
            </ul>
          {/if}
        </Card>
      </div>
    </div>
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
  .list {
    gap: 10px;
  }
  @media (max-width: 900px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
