<script lang="ts">
  import { onMount } from "svelte";
  import CircleAlert from "@lucide/svelte/icons/circle-alert";
  import House from "@lucide/svelte/icons/house";
  import Plus from "@lucide/svelte/icons/plus";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import RotateCcw from "@lucide/svelte/icons/rotate-ccw";
  import { DaemonUnavailableError } from "$lib/api/errors";
  import type { HomeCard, HomePage, HomeSection } from "$lib/api/types";
  import { beforeOf } from "$lib/chat/cardLayout";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { restoresOnEscape, toggled } from "$lib/fullScreen";
  import {
    CONVERSATIONS,
    dayOf,
    moved,
    movedBefore,
    updatedLabel,
    whileVisible,
    withColumns,
    withConversations,
    withSection,
    withoutSection,
  } from "$lib/home";
  import { t } from "$lib/i18n.svelte";
  import { HomeSaves } from "$lib/homeSaves.svelte";
  import { describe } from "$lib/notices";
  import { installedIcon } from "$lib/pluginIcons";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import HomeConversations from "$lib/ui/home/HomeConversations.svelte";
  import SectionCard from "$lib/ui/home/SectionCard.svelte";
  import SectionEditor from "$lib/ui/home/SectionEditor.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  // Home (core/home/): each section the assistant built from the plugins, as it was last saved. Showing it starts a
  // refresh in the background (the daemon skips it when the last one is under ten minutes old, today), and while
  // it's visible the daemon refreshes it every half hour; each section shows its new result as it's saved (a
  // `home` event).
  const { client, hub, notices } = useDaemon();
  const home = resource((c) => c.home.get(), ["home"]);
  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const plugins = $derived((servers.data ?? []).filter((s) => s.transport !== "none").map((s) => s.name));
  const sections = $derived(home.data?.cards.map((c) => c.section) ?? []);
  const refreshing = $derived(home.data?.refreshing ?? false);
  // Moving, removing and saving a section build on the list last asked for, so quick clicks add up.
  const saves = new HomeSaves(async (next) => show(await client.home.saveSections(next)));
  // Each card's width as last asked for, so a resized card doesn't spring back while its save is on its way.
  const widths = $derived(new Map(saves.latest(sections).map((s) => [s.id, s.columns])));

  // The clock the labels read, moved on every minute so "Updated" and the days stay right.
  let now = $state(new Date());
  const today = $derived(dayOf(now));

  // The section being edited: null for a new one; undefined when the editor is closed.
  let editing = $state<HomeSection | null | undefined>(undefined);
  let editError = $state("");
  let removing = $state<HomeSection | null>(null);
  let resetting = $state(false);
  // The card shown full screen, by its section's id; its button or Esc gives the page back.
  let maximized = $state<string | null>(null);
  const shownFull = $derived(home.data?.cards.find((c) => c.section.id === maximized) ?? null);
  // The card being dragged to another place, and where it would go.
  let dragged: string | null = null;
  let mark = $state<{ id: string; after: boolean } | null>(null);

  let visible = false;

  onMount(() => {
    const stop = whileVisible(document, shown, () => {
      visible = false;
      void inBackground(() => client.home.unwatch());
    });
    // A restarted daemon has forgotten that this tab shows Home.
    const reconnected = hub.onReconnect(() => visible && shown());
    const tick = setInterval(() => (now = new Date()), 60_000);
    return () => {
      reconnected();
      stop();
      clearInterval(tick);
    };
  });

  function shown(): void {
    visible = true;
    now = new Date();
    void inBackground(() => client.home.watch());
    void inBackground(async () => show(await client.home.refresh(false)));
  }

  // What showing Home does on its own: while the daemon can't be reached the banner says so, and it's done again
  // once the daemon is back (onReconnect), so only other errors are reported.
  async function inBackground(request: () => Promise<void>): Promise<void> {
    try {
      await request();
    } catch (e) {
      if (!(e instanceof DaemonUnavailableError)) notices.report(e);
    }
  }

  function show(page: HomePage): void {
    home.data = page;
  }

  async function refresh(): Promise<void> {
    try {
      show(await client.home.refresh(true));
    } catch (e) {
      notices.report(e);
    }
  }

  // The daemon builds the new and changed sections in the background.
  async function saveEdited(section: HomeSection): Promise<void> {
    try {
      await saves.send(withSection(saves.latest(sections), section));
      editing = undefined;
    } catch (e) {
      editError = describe(e);
    }
  }

  async function change(edit: (latest: HomeSection[]) => HomeSection[]): Promise<void> {
    try {
      await saves.send(edit(saves.latest(sections)));
    } catch (e) {
      notices.report(e);
    }
  }

  function remove(section: HomeSection): void {
    removing = null;
    void change((latest) => withoutSection(latest, section.id ?? ""));
  }

  async function reset(): Promise<void> {
    resetting = false;
    try {
      show(await client.home.resetSections());
    } catch (e) {
      notices.report(e);
    }
  }

  function edit(section: HomeSection | null): void {
    editError = "";
    editing = section;
  }

  // Built in, it can be removed; the editor of a new section offers it back.
  const hasConversations = $derived(sections.some((s) => s.id === CONVERSATIONS));
  async function addConversations(): Promise<void> {
    editing = undefined;
    await change((latest) => withConversations(latest, t("homeConversations.title")));
  }

  function keydown(e: KeyboardEvent): void {
    if (maximized !== null && restoresOnEscape(e, document)) maximized = null;
  }

  function dragStart(e: DragEvent, id: string): void {
    if (!e.dataTransfer) return;
    dragged = id;
    // Some browsers drag only what carries data.
    e.dataTransfer.setData("application/x-lo9i-home-card", id);
    e.dataTransfer.effectAllowed = "move";
    const whole = (e.currentTarget as HTMLElement).closest("section");
    if (whole) e.dataTransfer.setDragImage(whole, 16, 16);
  }

  function dragEnd(): void {
    dragged = null;
    mark = null;
  }

  /** Past the middle of the card dragged over: the drop goes after it. */
  function past(e: DragEvent): boolean {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return e.clientX > box.left + box.width / 2;
  }

  function dragOver(e: DragEvent, id: string): void {
    if (dragged === null) return;
    e.preventDefault();
    mark = { id, after: past(e) };
  }

  function dropOn(e: DragEvent, id: string): void {
    const card = dragged;
    if (card === null) return;
    e.preventDefault();
    const after = past(e);
    dragEnd();
    void change((latest) =>
      movedBefore(
        latest,
        card,
        beforeOf(
          latest.map((s) => s.id ?? ""),
          id,
          after,
        ),
      ),
    );
  }

  function dropMark(id: string): "before" | "after" | null {
    return mark?.id === id ? (mark.after ? "after" : "before") : null;
  }
</script>

<svelte:window onkeydown={keydown} ondragend={dragEnd} />

{#snippet sectionCard(card: HomeCard, i: number, full: boolean)}
  {@const id = card.section.id ?? ""}
  <SectionCard
    {card}
    columns={widths.get(card.section.id) ?? card.section.columns}
    icon={installedIcon(servers.data, card.section.plugins[0] ?? "")}
    {today}
    {refreshing}
    first={i === 0}
    last={i === (home.data?.cards.length ?? 0) - 1}
    onedit={() => edit(card.section)}
    ondelete={() => (removing = card.section)}
    onmove={(by) => change((latest) => moved(latest, id, by))}
    onresize={(columns) => change((latest) => withColumns(latest, id, columns))}
    maximized={full}
    onmaximize={() => (maximized = toggled(maximized, id))}
    ondragstart={(e) => dragStart(e, id)}
    ondragover={(e) => dragOver(e, id)}
    ondrop={(e) => dropOn(e, id)}
    drop={full ? null : dropMark(id)}
    children={id === CONVERSATIONS ? conversations : undefined}
  />
{/snippet}

{#snippet conversations()}
  <HomeConversations />
{/snippet}

<TopBar title={t("nav.home")}>
  {#snippet actions()}
    {#if home.data?.updated_at}<span class="text-meta hide-narrow">{updatedLabel(home.data.updated_at, now)}</span>{/if}
    <button class="btn btn--ghost" onclick={() => edit(null)}><Plus size={16} /><span class="hide-narrow">{t("homePage.add")}</span></button
    >
    <button class="btn btn--primary" disabled={refreshing} onclick={refresh}>
      <span class="icon" class:spinning={refreshing}><RefreshCw size={16} /></span><span class="hide-narrow"
        >{refreshing ? t("homePage.refreshing") : t("common.refresh")}</span
      >
    </button>
  {/snippet}
</TopBar>

<div class="screen">
  {#if home.error && !home.data}
    <section class="surface--glass">
      <EmptyState icon={CircleAlert} title={t("homePage.couldntLoad")} text={home.error} />
    </section>
  {:else if home.data === undefined}
    <p class="text-meta">{t("common.loading")}</p>
  {:else if home.data.cards.length === 0}
    <section class="surface--glass">
      <EmptyState icon={House} title={t("homePage.none")} text={t("homePage.noneHint")} />
    </section>
  {:else}
    <div class="grid">
      {#each home.data.cards as card, i (card.section.id)}
        {@render sectionCard(card, i, false)}
      {/each}
    </div>
    <!-- Outside the grid, whose container query would hold a fixed card inside it. -->
    {#if shownFull}
      {@render sectionCard(shownFull, home.data.cards.indexOf(shownFull), true)}
    {/if}
  {/if}
  <footer class="text-meta">
    {t("homePage.footer")}
    <button class="btn btn--ghost btn--sm" onclick={() => (resetting = true)}><RotateCcw size={14} />{t("homePage.builtIn")}</button>
  </footer>
</div>

{#if editing !== undefined}
  <SectionEditor
    section={editing}
    {plugins}
    error={editError}
    onsave={saveEdited}
    onclose={() => (editing = undefined)}
    onaddconversations={editing === null && !hasConversations ? addConversations : undefined}
  />
{/if}

{#if removing}
  {@const section = removing}
  <Confirm
    title={t("homePage.removeTitle", { title: section.title })}
    text={t("homePage.removeText")}
    action={t("common.remove")}
    onanswer={(yes) => (yes ? remove(section) : (removing = null))}
  />
{/if}

{#if resetting}
  <Confirm
    title={t("homePage.resetTitle")}
    text={t("homePage.resetText")}
    action={t("prompt.resetAction")}
    onanswer={(yes) => (yes ? reset() : (resetting = false))}
  />
{/if}

<style>
  .screen {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 0 16px 16px;
    max-width: 1600px;
    margin: 0 auto;
  }
  /* Its width is what the cards ask about to span their columns (SectionCard); dense fills the hole a wide card
   leaves at the end of a row with the cards after it. */
  .grid {
    container: home-grid / inline-size;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr));
    grid-auto-flow: dense;
    gap: 16px;
    align-items: start;
  }
  footer {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 12px;
  }
  .icon {
    display: inline-flex;
  }
  .spinning {
    animation: spin 0.9s linear infinite;
  }
</style>
