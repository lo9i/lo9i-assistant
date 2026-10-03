<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import Bell from "@lucide/svelte/icons/bell";
  import CalendarClock from "@lucide/svelte/icons/calendar-clock";
  import ChartColumn from "@lucide/svelte/icons/chart-column";
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import Files from "@lucide/svelte/icons/files";
  import Laptop from "@lucide/svelte/icons/laptop";
  import MessagesSquare from "@lucide/svelte/icons/messages-square";
  import MonitorSmartphone from "@lucide/svelte/icons/monitor-smartphone";
  import Plus from "@lucide/svelte/icons/plus";
  import Settings from "@lucide/svelte/icons/settings";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import PanelsTopLeft from "@lucide/svelte/icons/panels-top-left";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { pageLabel } from "$lib/pages";
  import { sidebar } from "$lib/sidebar.svelte";
  import VoiceButton from "./voice/VoiceButton.svelte";

  let { name }: { name: string } = $props();

  const { chat } = useDaemon();
  // MCP servers that come with a web page, shown in an iframe (routes/pages/[name]).
  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const pages = $derived((servers.data ?? []).filter((s) => s.page && s.enabled));
  // Failures are stored with the servers and skills, so their events refresh the count.
  const alerts = resource((c) => c.alerts.list(), ["mcp", "skills"]);
  // A new listing of the extras, an install or update, or the setting changes what's newer.
  const updates = resource((c) => c.repositories.updates(), ["plugins", "mcp", "skills", "settings"]);

  // The latest conversations, under Conversations, to continue one in a click.
  const RECENT = 10;
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const recent = $derived([...(conversations.data ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, RECENT));
  const current = external(chat.subscribe, () => chat.getSnapshot().threadId);

  async function continueWith(threadId: string): Promise<void> {
    await chat.resume(threadId);
    await goto(resolve("/conversations/open"));
  }

  type Add = { label: string; run: () => Promise<void> };

  async function newConversation(): Promise<void> {
    await chat.startNew();
    await goto(resolve("/conversations/open"));
  }

  // The devices page opens a pairing code when it sees ?pair.
  async function pairBrowser(): Promise<void> {
    await goto(`${resolve("/devices")}?pair`);
  }

  type Item = { href: string; label: string; Icon: typeof Plus; add?: Add; count?: () => number; also?: string[] };
  const NAV: Item[] = [
    {
      href: resolve("/conversations"),
      label: "Conversations",
      Icon: MessagesSquare,
      add: { label: "New conversation", run: newConversation },
    },
    { href: resolve("/files"), label: "Files", Icon: Files },
    { href: resolve("/usage"), label: "Usage", Icon: ChartColumn },
    { href: resolve("/sessions"), label: "Active sessions", Icon: MonitorSmartphone },
    { href: resolve("/jobs"), label: "Scheduled", Icon: CalendarClock },
    { href: resolve("/devices"), label: "Devices", Icon: Laptop, add: { label: "Pair a browser", run: pairBrowser } },
    { href: resolve("/alerts"), label: "Alerts", Icon: Bell, count: () => alerts.data?.length ?? 0 },
    // About you, Skills, Plugins and MCP servers are settings tabs with pages of their own; plugin updates show here.
    {
      href: resolve("/settings"),
      label: "Settings",
      Icon: Settings,
      also: [resolve("/memory"), resolve("/skills"), resolve("/plugins"), resolve("/mcp")],
      count: () => updates.data?.length ?? 0,
    },
  ];
</script>

<aside class="sidebar">
  <div class="brand">
    <span class="mark"><Sparkles size={16} /></span>
    <span class="brand-name label">{name}</span>
    <button
      class="collapse"
      aria-label={sidebar.collapsed ? "Expand sidebar" : "Collapse sidebar"}
      title="Toggle sidebar (⌘B)"
      onclick={() => sidebar.toggle()}
    >
      <ChevronLeft size={18} />
    </button>
  </div>
  <nav aria-label="Pages">
    {#each NAV as item (item.href)}
      {@const active = [item.href, ...(item.also ?? [])].some((href) => page.url.pathname.startsWith(href))}
      <div class="nav-row">
        <a href={item.href} class="nav-item" aria-current={active ? "page" : undefined} title={item.label}>
          <item.Icon size={20} />
          <span class="label">{item.label}</span>
          {#if item.count?.()}<span class="count" aria-label="{item.count()} new">{item.count()}</span>{/if}
        </a>
        {#if item.add}
          {@const add = item.add}
          <button class="add" aria-label={add.label} title={add.label} onclick={() => add.run()}>
            <Plus size={16} />
          </button>
        {/if}
      </div>
      {#if item.href === resolve("/conversations") && recent.length}
        <ul class="recent" aria-label="Recent conversations">
          {#each recent as c (c.thread_id)}
            <li>
              <button class:current={c.thread_id === current.current} title={c.title} onclick={() => continueWith(c.thread_id)}>
                {c.title || "Untitled"}
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    {/each}
    {#each pages as p (p.name)}
      {@const href = resolve("/pages/[name]", { name: p.name })}
      <div class="nav-row">
        <a {href} class="nav-item" aria-current={page.url.pathname === href ? "page" : undefined} title={pageLabel(p.name)}>
          <PanelsTopLeft size={20} />
          <span class="label">{pageLabel(p.name)}</span>
        </a>
      </div>
    {/each}
  </nav>
  <div class="voice-slot"><VoiceButton /></div>
</aside>

<style>
  .sidebar {
    position: sticky;
    top: 16px;
    height: calc(100vh - 32px);
    margin: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    overflow: hidden;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sidebar);
    background: var(--sidebar-bg);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 16px;
    border-bottom: 1px solid var(--color-border);
  }
  .mark {
    display: grid;
    place-items: center;
    flex: none;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-brand) 18%, transparent);
    color: var(--color-brand);
  }
  .brand-name {
    flex: 1;
    font-size: var(--font-size-md);
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .collapse {
    display: grid;
    place-items: center;
    flex: none;
    width: 28px;
    height: 28px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
    transition:
      background 0.12s ease,
      transform 0.18s ease;
  }
  .collapse:hover {
    background: var(--color-bg-hover-ghost);
  }
  nav {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding-inline: 8px;
    overflow-y: auto;
  }
  .voice-slot {
    display: flex;
    justify-content: center;
    padding: 12px 8px;
    border-top: 1px solid var(--color-border);
  }
  .nav-item {
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border: 0;
    border-radius: var(--radius-md);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--font-size-sm);
    font-weight: 500;
    text-decoration: none;
    white-space: nowrap;
    cursor: pointer;
    transition:
      background 0.12s ease,
      color 0.12s ease;
  }
  .nav-row {
    position: relative;
    display: flex;
  }
  .nav-row .nav-item {
    flex: 1;
    min-width: 0;
  }
  /* On the icon's corner, so it shows with the sidebar collapsed too. */
  .count {
    position: absolute;
    top: 4px;
    left: 24px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: var(--radius-full);
    background: var(--color-danger);
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    line-height: 16px;
    text-align: center;
  }
  .add {
    position: absolute;
    top: 50%;
    right: 6px;
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    transform: translateY(-50%);
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
    transition:
      background 0.12s ease,
      color 0.12s ease;
  }
  .add:hover {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  .nav-item:hover,
  .nav-item[aria-current="page"] {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  .nav-item[aria-current="page"]::before {
    content: "";
    position: absolute;
    left: 0;
    top: 8px;
    bottom: 8px;
    width: 3px;
    border-radius: 0 2px 2px 0;
    background: var(--color-accent);
  }
  .recent {
    list-style: none;
    margin: 0 0 4px;
    padding: 0 0 0 30px;
    display: flex;
    flex-direction: column;
  }
  .recent button {
    width: 100%;
    padding: 5px 8px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: pointer;
  }
  .recent button:hover,
  .recent button.current {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  :global(.collapsed) .recent {
    display: none;
  }
  :global(.collapsed) .label,
  :global(.collapsed) .mark {
    display: none;
  }
  :global(.collapsed) .brand {
    justify-content: center;
    padding: 16px 0;
  }
  :global(.collapsed) .collapse {
    transform: rotate(180deg);
  }
  :global(.collapsed) .nav-item {
    justify-content: center;
    padding: 10px 0;
  }
  :global(.collapsed) .add {
    display: none;
  }
  @media (max-width: 680px) {
    .label,
    .mark,
    .collapse,
    .add,
    .recent {
      display: none;
    }
    .nav-item {
      justify-content: center;
      padding: 10px 0;
    }
  }
</style>
