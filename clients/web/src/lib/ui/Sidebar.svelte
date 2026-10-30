<script lang="ts">
  let tip = $state<{ title: string; status: string; color: string; x: number; y: number } | null>(null);
  function showTip(e: Event, title: string, status: string, color: string) {
    // Past the whole row, not just its title: there it would cover the row's own buttons (Open beside, close).
    const target = e.currentTarget as HTMLElement;
    const r = (target.closest("li") ?? target).getBoundingClientRect();
    tip = { title, status, color, x: r.right + 10, y: r.top + r.height / 2 };
  }
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import Bell from "@lucide/svelte/icons/bell";
  import TextButton from "./quick/TextButton.svelte";
  import VoiceButton from "./quick/VoiceButton.svelte";
  import CalendarClock from "@lucide/svelte/icons/calendar-clock";
  import ChartColumn from "@lucide/svelte/icons/chart-column";
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import Columns2 from "@lucide/svelte/icons/columns-2";
  import Files from "@lucide/svelte/icons/files";
  import House from "@lucide/svelte/icons/house";
  import Laptop from "@lucide/svelte/icons/laptop";
  import MessageSquare from "@lucide/svelte/icons/message-square";
  import ListChecks from "@lucide/svelte/icons/list-checks";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import MessageCircle from "@lucide/svelte/icons/message-circle";
  import MonitorSmartphone from "@lucide/svelte/icons/monitor-smartphone";
  import Plus from "@lucide/svelte/icons/plus";
  import Settings from "@lucide/svelte/icons/settings";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import X from "@lucide/svelte/icons/x";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t, type Key } from "$lib/i18n.svelte";
  import { pageLabel } from "$lib/pages";
  import PluginIcon from "./PluginIcon.svelte";
  import { columnsOf } from "$lib/chat/cardLayout";
  import { conversationLayout } from "$lib/conversationLayout.svelte";
  import { CONVERSATION_DRAG, openBeside, startNewHere } from "./openConversation";
  import { OPEN_PAGE, openNow } from "./openNow.svelte";
  import { sidebar } from "$lib/sidebar.svelte";

  let { name }: { name: string } = $props();

  const { chats, notices } = useDaemon();
  // MCP servers that come with a web page, shown in an iframe (routes/pages/[name]).
  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const pages = $derived((servers.data ?? []).filter((s) => s.page && s.enabled));
  // Failures are stored with the servers and skills, and the health check's with its reports, so their events refresh
  // the count.
  const alerts = resource((c) => c.alerts.list(), ["mcp", "skills", "doctor"]);
  // A new listing of the extras, an install or update, or the setting changes what's newer.
  const updates = resource((c) => c.repositories.updates(), ["plugins", "mcp", "skills", "settings"]);
  // Job results and background work that ended, counted until the Notifications page is seen.
  const notifications = resource((c) => c.notifications.list(), ["notifications"]);
  const unread = $derived((notifications.data ?? []).filter((n) => !n.read).length);

  // Chat is the list of conversations. Under it: the ones open in this tab, side by side, and any other with
  // a reply or a coding task running, whoever started it. Open one to show it; the others keep going. Open beside, or
  // dragging one onto the conversation page, shows it next to the conversation shown there.
  const CHAT = resolve("/conversations");
  const OPEN = OPEN_PAGE;
  const open = openNow();
  const everything = $derived(open.items);
  // The conversations the conversation page shows together with the one shown there: they have no Open beside, and
  // their icon says they're together.
  const together = $derived.by(() => {
    const shown = everything.find((entry) => entry.active)?.threadId;
    return shown === undefined ? [] : columnsOf(conversationLayout.current, shown);
  });

  // On the conversation page with several shown, the new one joins them.
  async function startNew(): Promise<void> {
    if (page.url.pathname === OPEN) await startNewHere(chats, conversationLayout);
    else await chats.startNew();
    await goto(OPEN);
  }

  function dragConversation(e: DragEvent, threadId: string): void {
    if (!e.dataTransfer) return;
    e.dataTransfer.setData(CONVERSATION_DRAG, threadId);
    e.dataTransfer.effectAllowed = "copy";
  }

  type Add = { label: Key; run: () => Promise<void> };

  // The devices page opens a pairing code when it sees ?pair.
  async function pairBrowser(): Promise<void> {
    await goto(`${resolve("/devices")}?pair`);
  }

  type Item = {
    href: string;
    label: Key;
    Icon: typeof Plus;
    add?: Add;
    count?: () => number;
    // What the count counts, for screen readers; "new" when not given.
    counted?: Key;
    also?: string[];
    // Active only on this exact path, for a page with pages under it that have their own item.
    exact?: boolean;
  };
  const ALERTS = resolve("/alerts");
  const NOTIFICATIONS = resolve("/notifications");
  const NAV: Item[] = [
    { href: resolve("/home"), label: "nav.home", Icon: House },
    // The open conversations show under Chat. Its count is those waiting for an answer, for when that list is hidden
    // (the sidebar collapsed, a phone).
    {
      href: CHAT,
      label: "nav.chat",
      Icon: MessageCircle,
      add: { label: "nav.newConversation", run: startNew },
      exact: true,
      count: () => open.waiting,
      counted: "nav.waitingCount",
    },
    { href: resolve("/files"), label: "nav.files", Icon: Files },
    { href: resolve("/usage"), label: "nav.usage", Icon: ChartColumn },
    { href: resolve("/sessions"), label: "nav.sessions", Icon: MonitorSmartphone },
    { href: resolve("/jobs"), label: "nav.jobs", Icon: CalendarClock },
    { href: resolve("/devices"), label: "nav.devices", Icon: Laptop, add: { label: "nav.pairBrowser", run: pairBrowser } },
    { href: NOTIFICATIONS, label: "nav.notifications", Icon: ListChecks, count: () => unread },
    // About you, Skills, Plugins, MCP servers, Logs and Health are settings tabs with pages of their own; plugin updates
    // show here.
    {
      href: resolve("/settings"),
      label: "nav.settings",
      Icon: Settings,
      also: [resolve("/memory"), resolve("/skills"), resolve("/plugins"), resolve("/mcp"), resolve("/logs"), resolve("/doctor")],
      count: () => updates.data?.length ?? 0,
    },
  ];

  const tint = (id: string): string => open.tint(id);
</script>

<aside class="sidebar">
  <div class="brand">
    <span class="mark"><Sparkles size={16} /></span>
    <span class="brand-name label">{name}</span>
    <button
      class="collapse"
      aria-label={sidebar.collapsed ? t("nav.expand") : t("nav.collapse")}
      title={t("nav.toggle")}
      onclick={() => sidebar.toggle()}
    >
      <ChevronLeft size={18} />
    </button>
  </div>
  <nav aria-label={t("nav.pages")}>
    {#each NAV as item (item.href)}
      {@const active = item.exact
        ? page.url.pathname === item.href
        : [item.href, ...(item.also ?? [])].some((href) => page.url.pathname.startsWith(href))}
      <div class="nav-row">
        <a href={item.href} class="nav-item" aria-current={active ? "page" : undefined} title={t(item.label)}>
          <item.Icon size={20} />
          <span class="label">{t(item.label)}</span>
          {#if item.count?.()}<span class="count" aria-label={t(item.counted ?? "nav.newCount", { count: item.count() })}
              >{item.count()}</span
            >{/if}
        </a>
        {#if item.add}
          {@const add = item.add}
          <button class="add" aria-label={t(add.label)} title={t(add.label)} onclick={() => add.run()}>
            <Plus size={16} />
          </button>
        {/if}
      </div>
      {#if item.href === CHAT && everything.length}
        <ul class="open" aria-label={t("nav.openConversations")}>
          {#each everything as entry (entry.key ?? entry.threadId)}
            <li class="branch">
              <button
                class="branch-item"
                draggable="true"
                ondragstart={(e) => dragConversation(e, entry.threadId)}
                style:--tint={tint(entry.threadId)}
                class:current={entry.active && page.url.pathname === OPEN}
                aria-current={entry.active && page.url.pathname === OPEN ? "true" : undefined}
                onmouseenter={(e) =>
                  showTip(e, entry.title, entry.waiting ? t("nav.waiting") : entry.running ? t("nav.working") : "", tint(entry.threadId))}
                onmouseleave={() => (tip = null)}
                onfocus={(e) => showTip(e, entry.title, "", tint(entry.threadId))}
                onblur={() => (tip = null)}
                onclick={() => open.show(entry)}
              >
                {#if entry.running}<LoaderCircle size={14} class="spin" aria-label={t("nav.working")} />
                {:else if together.length > 1 && together.includes(entry.threadId)}<Columns2
                    size={14}
                    aria-label={t("nav.shownTogether")}
                  />
                {:else}<MessageSquare size={14} />{/if}
                <span>{entry.title}</span>
                {#if entry.waiting}<i class="waiting" aria-label={t("nav.waiting")}></i>{/if}
              </button>
              {#if !together.includes(entry.threadId)}
                <button
                  class="close beside"
                  aria-label={t("nav.openBeside", { title: entry.title })}
                  title={t("nav.openBesideHint")}
                  onclick={() => openBeside(chats, notices, conversationLayout, entry.threadId)}><Columns2 size={14} /></button
                >
              {/if}
              {#if entry.key !== null}
                {@const key = entry.key}
                <button
                  class="close"
                  aria-label={t("nav.closeConversation", { title: entry.title })}
                  title={t("common.close")}
                  onclick={() => open.close(key)}><X size={14} /></button
                >
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    {/each}
    {#if pages.length}<hr class="divider" />{/if}
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
    <!-- Last: alerts, and a short message or voice to the assistant (sent to the inbox, routed on). -->
    <div class="bar">
      <a
        href={ALERTS}
        class="bar-item"
        aria-current={page.url.pathname.startsWith(ALERTS) ? "page" : undefined}
        aria-label={t("nav.alerts")}
        title={t("nav.alerts")}
      >
        <Bell size={18} />
        {#if alerts.data?.length}<span class="count" aria-label={t("nav.newCount", { count: alerts.data.length })}
            >{alerts.data.length}</span
          >{/if}
      </a>
      <TextButton />
      <VoiceButton />
    </div>
  </div>
</aside>

{#if tip}
  <div class="conv-tip" role="tooltip" style="left: {tip.x}px; top: {tip.y}px">
    <span class="tip-title"><i style="background: {tip.color}"></i>{tip.title}</span>
    {#if tip.status}<span class="tip-status">{tip.status}</span>{/if}
  </div>
{/if}

<style>
  .conv-tip {
    position: fixed;
    transform: translateY(-50%);
    z-index: 100;
    max-width: 280px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px 12px;
    border: 1px solid var(--color-border);
    border-radius: 10px;
    background: var(--color-bg-page);
    box-shadow: var(--shadow-popover);
    font-size: 12px;
    line-height: 1.4;
    pointer-events: none;
    animation: tip-in 0.12s ease;
  }
  @keyframes tip-in {
    from {
      opacity: 0;
      transform: translate(-4px, -50%);
    }
  }
  .tip-title {
    display: flex;
    align-items: baseline;
    gap: 6px;
    color: var(--color-text-primary);
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  .tip-title i {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
  .tip-status {
    color: var(--color-text-muted);
  }
  .sidebar {
    position: sticky;
    /* Above the page, so the quick panels it holds aren't covered by the chat. */
    z-index: var(--z-popover);
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
    padding: 10px 16px;
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
  .divider {
    flex: none;
    margin: 4px 4px;
    border: 0;
    border-top: 1px solid var(--color-border);
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
    margin: 2px 0 4px 22px;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 0;
  }
  .branch {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .branch-item {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 8px;
    border: 0;
    border-left: 2px solid var(--tint);
    border-radius: 0;
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
    color: var(--color-text-muted);
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
  /* Open beside shows on the row the pointer is on, so the titles keep their room; always where nothing hovers. */
  @media (hover: hover) {
    .branch:not(:hover):not(:focus-within) .beside {
      display: none;
    }
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
    padding: 10px 0;
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
  .bar {
    display: flex;
    justify-content: space-around;
    gap: 4px;
    margin-top: 4px;
  }
  .bar :global(.bar-item) {
    position: relative;
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    border: 0;
    border-radius: var(--radius-md);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
    transition:
      background 0.12s ease,
      color 0.12s ease;
  }
  .bar :global(.bar-item:hover),
  .bar :global(.bar-item[aria-current="page"]) {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  .bar .count {
    top: 2px;
    left: 20px;
  }
  :global(.collapsed) .bar {
    flex-direction: column;
    align-items: center;
  }
  @media (max-width: 680px) {
    .bar {
      flex-direction: column;
      align-items: center;
    }
  }
</style>
