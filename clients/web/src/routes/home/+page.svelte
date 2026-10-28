<script lang="ts">
  import { onMount } from "svelte";
  import CircleAlert from "@lucide/svelte/icons/circle-alert";
  import House from "@lucide/svelte/icons/house";
  import Plus from "@lucide/svelte/icons/plus";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import RotateCcw from "@lucide/svelte/icons/rotate-ccw";
  import { DaemonUnavailableError } from "$lib/api/errors";
  import type { HomePage, HomeSection } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { dayOf, moved, updatedLabel, whileVisible, withSection, withoutSection } from "$lib/home";
  import { HomeSaves } from "$lib/homeSaves.svelte";
  import { describe } from "$lib/notices";
  import { installedIcon } from "$lib/pluginIcons";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
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

  // The clock the labels read, moved on every minute so "Updated" and the days stay right.
  let now = $state(new Date());
  const today = $derived(dayOf(now));

  // The section being edited: null for a new one; undefined when the editor is closed.
  let editing = $state<HomeSection | null | undefined>(undefined);
  let editError = $state("");
  let removing = $state<HomeSection | null>(null);
  let resetting = $state(false);

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
</script>

<TopBar title="Home">
  {#snippet actions()}
    {#if home.data?.updated_at}<span class="text-meta hide-narrow">{updatedLabel(home.data.updated_at, now)}</span>{/if}
    <button class="btn btn--ghost" onclick={() => edit(null)}><Plus size={16} /><span class="hide-narrow">Add section</span></button>
    <button class="btn btn--primary" disabled={refreshing} onclick={refresh}>
      <span class="icon" class:spinning={refreshing}><RefreshCw size={16} /></span><span class="hide-narrow"
        >{refreshing ? "Refreshing…" : "Refresh"}</span
      >
    </button>
  {/snippet}
</TopBar>

<div class="screen">
  {#if home.error && !home.data}
    <section class="surface--glass">
      <EmptyState icon={CircleAlert} title="Home couldn't load" text={home.error} />
    </section>
  {:else if home.data === undefined}
    <p class="text-meta">Loading…</p>
  {:else if home.data.cards.length === 0}
    <section class="surface--glass">
      <EmptyState icon={House} title="No sections" text="Add a section: say what to show, and the assistant builds it from your plugins." />
    </section>
  {:else}
    <div class="grid">
      {#each home.data.cards as card, i (card.section.id)}
        <SectionCard
          {card}
          icon={installedIcon(servers.data, card.section.plugins[0] ?? "")}
          {today}
          {refreshing}
          first={i === 0}
          last={i === home.data.cards.length - 1}
          onedit={() => edit(card.section)}
          ondelete={() => (removing = card.section)}
          onmove={(by) => change((latest) => moved(latest, card.section.id ?? "", by))}
        />
      {/each}
    </div>
  {/if}
  <footer class="text-meta">
    Each section is an instruction the assistant follows with your plugins' tools that only read. Home refreshes when you open it, at most
    every ten minutes.
    <button class="btn btn--ghost btn--sm" onclick={() => (resetting = true)}><RotateCcw size={14} />Use the built-in sections</button>
  </footer>
</div>

{#if editing !== undefined}
  <SectionEditor section={editing} {plugins} error={editError} onsave={saveEdited} onclose={() => (editing = undefined)} />
{/if}

{#if removing}
  {@const section = removing}
  <Confirm
    title="Remove {section.title}?"
    text="It goes from Home. The plugin and its data aren't touched."
    action="Remove"
    onanswer={(yes) => (yes ? remove(section) : (removing = null))}
  />
{/if}

{#if resetting}
  <Confirm
    title="Go back to the built-in sections?"
    text="Your sections are replaced by Calendario, Watchlist and Gastos."
    action="Reset"
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
  /* Its width is what the cards ask about to take two columns (SectionCard); dense fills the hole a wide card
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
