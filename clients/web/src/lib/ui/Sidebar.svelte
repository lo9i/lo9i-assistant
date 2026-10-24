<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import Bell from "@lucide/svelte/icons/bell";
  import CalendarClock from "@lucide/svelte/icons/calendar-clock";
  import ChartColumn from "@lucide/svelte/icons/chart-column";
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import Files from "@lucide/svelte/icons/files";
  import House from "@lucide/svelte/icons/house";
  import Laptop from "@lucide/svelte/icons/laptop";
  import CornerDownRight from "@lucide/svelte/icons/corner-down-right";
  import Inbox from "@lucide/svelte/icons/inbox";
  import ListChecks from "@lucide/svelte/icons/list-checks";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import MessageCircle from "@lucide/svelte/icons/message-circle";
  import MonitorSmartphone from "@lucide/svelte/icons/monitor-smartphone";
  import Plus from "@lucide/svelte/icons/plus";
  import Settings from "@lucide/svelte/icons/settings";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import X from "@lucide/svelte/icons/x";
  import { openList } from "$lib/chat/openList";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { pageLabel } from "$lib/pages";
  import PluginIcon from "./PluginIcon.svelte";
  import { sidebar } from "$lib/sidebar.svelte";

  let { name }: { name: string } = $props();

  const { chats, voice } = useDaemon();
  // MCP servers that come with a web page, shown in an iframe (routes/pages/[name]).
  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const pages = $derived((servers.data ?? []).filter((s) => s.page && s.enabled));
  // Failures are stored with the servers and skills, so their events refresh the count.
  const alerts = resource((c) => c.alerts.list(), ["mcp", "skills"]);
  // A new listing of the extras, an install or update, or the setting changes what's newer.
  const updates = resource((c) => c.repositories.updates(), ["plugins", "mcp", "skills", "settings"]);
  // Job results and background work that ended, counted until the Notifications page is seen.
  const notifications = resource((c) => c.notifications.list(), ["notifications"]);
  const unread = $derived((notifications.data ?? []).filter((n) => !n.read).length);

  // Chat is the list of conversations. Under it: the ones open in this tab, side by side, and any other with
  // a reply or a coding task running, whoever started it. Open one to show it; the others keep going.
  const CHAT = resolve("/conversations");
  const OPEN = resolve("/conversations/open");
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const runs = resource((c) => c.runs.inProgress(), ["run", "run_finished"]);
  const tasks = resource((c) => c.tasks.running(), ["agent_task_progress", "agent_task_reports", "background_ended"]);
  const open = external(chats.subscribe, chats.getSnapshot);
  const voiceThread = external(voice.subscribe, () => voice.getSnapshot().threadId);
  const everything = $derived(
    openList(open.current, conversations.data ?? [], [
      ...(runs.data ?? []).map((r) => r.thread_id),
      ...(tasks.data ?? []).map((t) => t.thread_id),
    ]).filter((item) => item.threadId !== voiceThread.current),
  );
  async function show(item: { key: string | null; threadId: string }): Promise<void> {
    if (item.key === null) await chats.show(item.threadId);
    else chats.activate(item.key);
    await goto(OPEN);
  }

  async function startNew(): Promise<void> {
    await chats.startNew();
    await goto(OPEN);
  }

  type Add = { label: string; run: () => Promise<void> };

  // The devices page opens a pairing code when it sees ?pair.
  async function pairBrowser(): Promise<void> {
    await goto(`${resolve("/devices")}?pair`);
  }

  type Item = {
    href: string;
    label: string;
    Icon: typeof Plus;
    add?: Add;
    count?: () => number;
    // What the count counts, for screen readers; "new" when not given.
    counted?: string;
    also?: string[];
    // Active only on this exact path, for a page with pages under it that have their own item.
    exact?: boolean;
  };
  const ALERTS = resolve("/alerts");
  const NOTIFICATIONS = resolve("/notifications");
  const NAV: Item[] = [
    { href: resolve("/home"), label: "Home", Icon: House },
    // The open conversations show under Chat. Its count is those waiting for an answer, for when that list is hidden
    // (the sidebar collapsed, a phone).
    {
      href: CHAT,
      label: "Chat",
      Icon: MessageCircle,
      add: { label: "New conversation", run: startNew },
      exact: true,
      count: () => everything.filter((entry) => entry.waiting).length,
      counted: "waiting for your answer",
    },
    { href: resolve("/files"), label: "Files", Icon: Files },
    { href: resolve("/usage"), label: "Usage", Icon: ChartColumn },
    { href: resolve("/sessions"), label: "Active sessions", Icon: MonitorSmartphone },
    { href: resolve("/jobs"), label: "Scheduled", Icon: CalendarClock },
    { href: resolve("/devices"), label: "Devices", Icon: Laptop, add: { label: "Pair a browser", run: pairBrowser } },
    // About you, Skills, Plugins, MCP servers and Logs are settings tabs with pages of their own; plugin updates show here.
    {
      href: resolve("/settings"),
      label: "Settings",
      Icon: Settings,
      also: [resolve("/memory"), resolve("/skills"), resolve("/plugins"), resolve("/mcp"), resolve("/logs")],
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
      {@const active = item.exact
        ? page.url.pathname === item.href
        : [item.href, ...(item.also ?? [])].some((href) => page.url.pathname.startsWith(href))}
      <div class="nav-row">
        <a href={item.href} class="nav-item" aria-current={active ? "page" : undefined} title={item.label}>
          <item.Icon size={20} />
          <span class="label">{item.label}</span>
          {#if item.count?.()}<span class="count" aria-label="{item.count()} {item.counted ?? 'new'}">{item.count()}</span>{/if}
        </a>
        {#if item.add}
          {@const add = item.add}
          <button class="add" aria-label={add.label} title={add.label} onclick={() => add.run()}>
            <Plus size={16} />
          </button>
        {/if}
      </div>
      {#if item.href === CHAT && everything.length}
        <ul class="open" aria-label="Open conversations">
          {#each everything as entry (entry.key ?? entry.threadId)}
            <li class="branch">
              <button
                class="branch-item"
                class:current={entry.active && page.url.pathname === OPEN}
                aria-current={entry.active && page.url.pathname === OPEN ? "true" : undefined}
                title={entry.title + (entry.waiting ? " · waiting for your answer" : entry.running ? " · working" : "")}
                onclick={() => show(entry)}
              >
                {#if entry.running}<LoaderCircle size={14} class="spin" aria-label="working" />
                {:else if entry.inbox}<Inbox size={14} />
                {:else}<CornerDownRight size={14} />{/if}
                <span>{entry.title}</span>
                {#if entry.waiting}<i class="waiting" aria-label="waiting for your answer"></i>{/if}
              </button>
              {#if entry.key !== null && open.current.chats.length > 1}
                {@const key = entry.key}
                <button class="close" aria-label="Close {entry.title}" title="Close" onclick={() => chats.close(key)}
                  ><X size={14} /></button
                >
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    {/each}
    {#each pages as p (p.name)}
      {@const href = resolve("/pages/[name]", { name: p.name })}
      <div class="nav-row">
        <a {href} class="nav-item" aria-current={page.url.pathname === href ? "page" : undefined} title={pageLabel(p.name)}>
          <PluginIcon icon={p.icon} size={20} />
          <span class="label">{pageLabel(p.name)}</span>
        </a>
      </div>
    {/each}
  </nav>
  <!-- At the bottom, on its own: what needs attention. -->
  <div class="footer-slot">
    <div class="nav-row">
      <a
        href={NOTIFICATIONS}
        class="nav-item"
        aria-current={page.url.pathname.startsWith(NOTIFICATIONS) ? "page" : undefined}
        title="Notifications"
      >
        <ListChecks size={20} />
        <span class="label">Notifications</span>
        {#if unread}<span class="count" aria-label="{unread} new">{unread}</span>{/if}
      </a>
    </div>
    <div class="nav-row">
      <a href={ALERTS} class="nav-item" aria-current={page.url.pathname.startsWith(ALERTS) ? "page" : undefined} title="Alerts">
        <Bell size={20} />
        <span class="label">Alerts</span>
        {#if alerts.data?.length}<span class="count" aria-label="{alerts.data.length} new">{alerts.data.length}</span>{/if}
      </a>
    </div>
  </div>
</aside>

<style>
  .sidebar {
    position: sticky;
    top: 8px;
    height: calc(100vh - 16px);
    margin: 8px 0 8px 8px;
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
  .footer-slot {
    padding: 8px;
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
  /* The conversations open in this tab, and others working, under Chat. */
  .open {
    margin: 0 0 4px;
    padding: 0;
    list-style: none;
  }
  .branch {
    display: flex;
    align-items: center;
    gap: 2px;
    padding-left: 22px;
  }
  .branch-item {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 8px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
    text-align: left;
    cursor: pointer;
  }
  .branch-item span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .branch-item :global(svg) {
    flex: none;
    color: var(--color-accent);
  }
  .waiting {
    flex: none;
    width: 8px;
    height: 8px;
    margin-left: auto;
    border-radius: var(--radius-full);
    background: var(--color-accent);
  }
  .branch-item :global(.spin) {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .branch-item :global(.spin) {
      animation: none;
    }
  }
  .close {
    display: grid;
    place-items: center;
    flex: none;
    width: 26px;
    height: 26px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .branch-item:hover,
  .branch-item.current,
  .close:hover {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  :global(.collapsed) .open {
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
    .open {
      display: none;
    }
    .nav-item {
      justify-content: center;
      padding: 10px 0;
    }
  }
</style>
