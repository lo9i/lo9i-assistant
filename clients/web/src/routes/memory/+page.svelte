<script lang="ts">
  import Briefcase from "@lucide/svelte/icons/briefcase";
  import Clock from "@lucide/svelte/icons/clock";
  import Heart from "@lucide/svelte/icons/heart";
  import MessageSquareText from "@lucide/svelte/icons/message-square-text";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import Target from "@lucide/svelte/icons/target";
  import ThumbsDown from "@lucide/svelte/icons/thumbs-down";
  import UserRound from "@lucide/svelte/icons/user-round";
  import Users from "@lucide/svelte/icons/users";
  import { startGetToKnowYou } from "$lib/chat/getToKnowYou";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { sectionLabel } from "$lib/memory";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import SettingsTabs from "$lib/ui/settings/SettingsTabs.svelte";

  // The profile sections (core/memory/profile.py); one the app doesn't know gets the person icon.
  const ICONS: Record<string, typeof UserRound> = {
    about: UserRound,
    people: Users,
    how_to_reply: MessageSquareText,
    routine: Clock,
    goals: Target,
    interests: Heart,
    dislikes: ThumbsDown,
    work: Briefcase,
  };

  // Read only: the assistant keeps this up to date from conversations, and changes it when asked in chat.
  const memory = resource((c) => c.memory.snapshot(), ["memory"]);
  const { chat } = useDaemon();
  const sections = $derived(Object.entries(memory.data?.profile ?? {}).filter(([, items]) => items.length));
</script>

<!-- A settings tab of its own page. -->
<TopBar title="Settings" />

<div class="shell">
  <SettingsTabs active="memory" />
  <header class="intro">
    <div>
      <h2 class="text-heading">Profile</h2>
      <p class="text-meta">Always in the assistant's mind. Changes apply from the next conversation.</p>
    </div>
    <button class="btn btn--neutral btn--sm" onclick={() => startGetToKnowYou(chat)}><Sparkles size={14} />Get to know me</button>
  </header>
  {#if memory.error}
    <p class="error-text">{memory.error}</p>
  {:else if memory.data && sections.length === 0}
    <section class="surface--glass empty">
      <EmptyState icon={UserRound} title="Nothing yet" text="The profile fills in as you talk." />
    </section>
  {:else if memory.data}
    <div class="grid">
      {#each sections as [name, items] (name)}
        {@const Icon = ICONS[name] ?? UserRound}
        <section class="section surface--glass">
          <header>
            <span class="icon"><Icon size={16} /></span>
            <h3 class="micro-label">{sectionLabel(name)}</h3>
            <span class="pill">{items.length}</span>
          </header>
          <ul>
            {#each items as item, i (i)}<li>{item}</li>{/each}
          </ul>
        </section>
      {/each}
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
  .intro {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    padding: 8px 4px 0;
  }
  .intro p {
    margin: 4px 0 0;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(360px, 100%), 1fr));
    gap: 16px;
    align-items: start;
  }
  .section {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 20px;
  }
  .section header {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .icon {
    display: grid;
    place-items: center;
    flex: none;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-brand) 18%, transparent);
    color: var(--color-brand);
  }
  h3 {
    flex: 1;
    margin: 0;
  }
  ul {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding-left: 18px;
    overflow-wrap: anywhere;
  }
  li::marker {
    color: var(--color-text-muted);
  }
  .empty {
    padding: 24px;
  }
</style>
