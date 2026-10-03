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
  import TopBar from "$lib/ui/TopBar.svelte";
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
  const { chat, client, notices } = useDaemon();

  async function saveSection(name: string, items: string[]): Promise<void> {
    try {
      await client.memory.setProfileSection(name, items);
    } catch (e) {
      notices.report(e);
    }
    memory.reload();
  }
</script>

<!-- A settings tab of its own page. -->
<TopBar title="Settings">
  {#snippet actions()}
    <button class="btn btn--primary" onclick={() => startGetToKnowYou(chat)}
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
</style>
