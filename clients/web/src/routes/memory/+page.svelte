<script lang="ts">
  import BookOpen from "@lucide/svelte/icons/book-open";
  import Briefcase from "@lucide/svelte/icons/briefcase";
  import Lightbulb from "@lucide/svelte/icons/lightbulb";
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
  import TopBar from "$lib/ui/TopBar.svelte";
  import MemoryList from "$lib/ui/memory/MemoryList.svelte";
  import ProfileSection from "$lib/ui/memory/ProfileSection.svelte";
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

  // The assistant keeps this up to date from conversations; the user adds and edits items here too.
  const memory = resource((c) => c.memory.snapshot(), ["memory"]);
  const { chats, client, notices } = useDaemon();

  // What it saved on its own: facts, and a summary of each past conversation.
  const facts = resource((c) => c.memory.facts(), ["memory"]);
  const episodes = resource((c) => c.memory.episodes(), ["memory"]);
  const factItems = $derived((facts.data ?? []).map((f) => ({ id: f.id, text: f.text, when: f.saved_at.slice(0, 10) })));
  const episodeItems = $derived((episodes.data ?? []).map((e) => ({ id: e.id ?? "", text: e.summary, when: e.started_at.slice(0, 10) })));

  async function saveSection(name: string, items: string[]): Promise<void> {
    try {
      await client.memory.setProfileSection(name, items);
    } catch (e) {
      notices.report(e);
    }
    memory.reload();
  }

  /** Lists reload from the `memory` event every change publishes. */
  async function change(call: () => Promise<unknown>): Promise<void> {
    try {
      await call();
    } catch (e) {
      notices.report(e);
    }
  }
</script>

<!-- A settings tab of its own page. -->
<TopBar title="Settings">
  {#snippet actions()}
    <button class="btn btn--primary" onclick={() => startGetToKnowYou(chats)}
      ><Sparkles size={16} /><span class="hide-narrow">Get to know me</span></button
    >
  {/snippet}
</TopBar>

<div class="shell">
  <SettingsTabs active="memory" />
  <header class="intro">
    <h2 class="text-heading">Profile</h2>
    <p class="text-meta">Always in the assistant's mind. Changes apply from the next conversation.</p>
  </header>
  {#if memory.error}
    <p class="error-text">{memory.error}</p>
  {:else if memory.data}
    <div class="grid">
      {#each memory.data.profile_sections as name (name)}
        <ProfileSection
          {name}
          items={memory.data.profile?.[name] ?? []}
          Icon={ICONS[name] ?? UserRound}
          onsave={(items) => saveSection(name, items)}
        />
      {/each}
    </div>
  {/if}
  <header class="intro">
    <h2 class="text-heading">Saved along the way</h2>
    <p class="text-meta">What the assistant noted in conversations. The newest facts are in its mind; it searches the rest.</p>
  </header>
  {#if facts.error || episodes.error}
    <p class="error-text">{facts.error ?? episodes.error}</p>
  {:else}
    <div class="lists">
      <MemoryList
        title="Facts"
        noun="fact"
        items={factItems}
        Icon={Lightbulb}
        onedit={(id, text) => change(() => client.memory.editFact(id, text))}
        ondelete={(id) => change(() => client.memory.deleteFact(id))}
      />
      <MemoryList
        title="Conversation summaries"
        noun="summary"
        items={episodeItems}
        Icon={BookOpen}
        onedit={(id, text) => change(() => client.memory.editEpisode(id, text))}
        ondelete={(id) => change(() => client.memory.deleteEpisode(id))}
      />
    </div>
  {/if}
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 0 16px 40px;
    max-width: 1600px;
    margin: 0 auto;
  }
  .intro {
    padding: 8px 4px 0;
  }
  .intro p {
    margin: 4px 0 0;
  }
  .lists {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(520px, 100%), 1fr));
    gap: 16px;
    align-items: start;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(360px, 100%), 1fr));
    gap: 16px;
    align-items: start;
  }
</style>
