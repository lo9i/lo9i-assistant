<script lang="ts">
  import Briefcase from "@lucide/svelte/icons/briefcase";
  import Lightbulb from "@lucide/svelte/icons/lightbulb";
  import Clock from "@lucide/svelte/icons/clock";
  import Heart from "@lucide/svelte/icons/heart";
  import MessageSquareText from "@lucide/svelte/icons/message-square-text";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import UserRoundPen from "@lucide/svelte/icons/user-round-pen";
  import Target from "@lucide/svelte/icons/target";
  import ThumbsDown from "@lucide/svelte/icons/thumbs-down";
  import UserRound from "@lucide/svelte/icons/user-round";
  import Users from "@lucide/svelte/icons/users";
  import { aboutYouStep } from "$lib/aboutYou.svelte";
  import { startGetToKnowYou } from "$lib/chat/getToKnowYou";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { placed, stepped } from "$lib/memory";
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

  // What it saved on its own: facts.
  const facts = resource((c) => c.memory.facts(), ["memory"]);
  const factItems = $derived((facts.data ?? []).map((f) => ({ id: f.id, text: f.text, when: f.saved_at.slice(0, 10) })));

  async function saveSection(name: string, items: string[]): Promise<void> {
    try {
      await client.memory.setProfileSection(name, items);
    } catch (e) {
      notices.report(e);
    }
    memory.reload();
  }

  // The sections' order as the user set it, by dragging a card's handle or with its arrow keys: shown at once, until
  // the daemon's snapshot has it.
  let moved = $state<string[] | null>(null);
  const order = $derived(moved ?? memory.data?.profile_sections ?? []);
  $effect(() => {
    if (moved && memory.data?.profile_sections?.join() === moved.join()) moved = null;
  });

  async function reorder(next: string[]): Promise<void> {
    if (next === order) return;
    moved = next;
    try {
      await client.memory.setProfileOrder(next);
    } catch (e) {
      moved = null;
      notices.report(e);
    }
    memory.reload();
  }

  // The section being dragged, and the one under the pointer with where it would go. Pointer events, so a mouse, a
  // finger and a pen drag the same way; the pointer is captured by the handle, so the drop is found by position.
  let dragging = $state<string | null>(null);
  let mark = $state<{ name: string; after: boolean } | null>(null);

  function grab(e: PointerEvent, name: string): void {
    if (e.button !== 0) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragging = name;
  }

  function drag(e: PointerEvent): void {
    if (dragging === null) return;
    const over = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>("[data-section]");
    const name = over?.dataset.section;
    if (!over || !name || name === dragging) {
      mark = null;
      return;
    }
    const box = over.getBoundingClientRect();
    mark = { name, after: e.clientY > box.top + box.height / 2 };
  }

  function release(): void {
    const name = dragging;
    const target = mark;
    dragging = null;
    mark = null;
    if (name !== null && target !== null) void reorder(placed(order, name, target.name, target.after));
  }

  function cancelDrag(): void {
    dragging = null;
    mark = null;
  }

  function keydown(e: KeyboardEvent): void {
    if (e.key === "Escape" && dragging !== null) cancelDrag();
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

<svelte:window onpointermove={drag} onpointerup={release} onpointercancel={cancelDrag} onkeydown={keydown} />

<!-- A settings tab of its own page. -->
<TopBar title={t("nav.settings")}>
  {#snippet actions()}
    <button class="btn btn--neutral" onclick={() => (aboutYouStep.open = true)}
      ><UserRoundPen size={16} /><span class="hide-narrow">{t("memoryPage.aboutYou")}</span></button
    >
    <button class="btn btn--primary" onclick={() => startGetToKnowYou(chats)}
      ><Sparkles size={16} /><span class="hide-narrow">{t("memoryPage.getToKnowMe")}</span></button
    >
  {/snippet}
</TopBar>

<div class="shell">
  <SettingsTabs active="memory" />
  {#if memory.error}
    <p class="error-text">{memory.error}</p>
  {:else if memory.data}
    <div class="grid">
      {#each order as name (name)}
        <ProfileSection
          {name}
          items={memory.data.profile?.[name] ?? []}
          Icon={ICONS[name] ?? UserRound}
          onsave={(items) => saveSection(name, items)}
          ongrab={(e) => grab(e, name)}
          onstep={(by) => reorder(stepped(order, name, by))}
          lifted={dragging === name}
          drop={mark?.name === name ? (mark.after ? "after" : "before") : null}
        />
      {/each}
    </div>
  {/if}
  <header class="intro">
    <h2 class="text-heading">{t("memoryPage.saved")}</h2>
    <p class="text-meta">{t("memoryPage.savedHint")}</p>
  </header>
  {#if facts.error}
    <p class="error-text">{facts.error}</p>
  {:else}
    <div class="lists">
      <MemoryList
        title={t("memoryPage.facts")}
        noun={t("memoryPage.fact")}
        items={factItems}
        Icon={Lightbulb}
        onedit={(id, text) => change(() => client.memory.editFact(id, text))}
        ondelete={(id) => change(() => client.memory.deleteFact(id))}
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
  /* Columns rather than a grid: a short section sits right under the one above it, instead of leaving
     the space a long neighbor takes in its row. */
  .grid {
    column-width: 360px;
    column-gap: 16px;
    /* The last section's margin, so the page's gap alone separates what follows. */
    margin-bottom: -16px;
  }
  .grid > :global(*) {
    break-inside: avoid;
    margin-bottom: 16px;
  }
</style>
