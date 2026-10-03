<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import Blocks from "@lucide/svelte/icons/blocks";
  import CalendarClock from "@lucide/svelte/icons/calendar-clock";
  import ChartColumn from "@lucide/svelte/icons/chart-column";
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import Laptop from "@lucide/svelte/icons/laptop";
  import MessagesSquare from "@lucide/svelte/icons/messages-square";
  import MonitorSmartphone from "@lucide/svelte/icons/monitor-smartphone";
  import Plus from "@lucide/svelte/icons/plus";
  import Puzzle from "@lucide/svelte/icons/puzzle";
  import Settings from "@lucide/svelte/icons/settings";
  import UserRound from "@lucide/svelte/icons/user-round";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import SunMoon from "@lucide/svelte/icons/sun-moon";
  import WandSparkles from "@lucide/svelte/icons/wand-sparkles";
  import PanelsTopLeft from "@lucide/svelte/icons/panels-top-left";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { pageLabel } from "$lib/pages";
  import { sidebar } from "$lib/sidebar.svelte";
  import { theme, type ThemePreference } from "$lib/theme.svelte";

  let { name }: { name: string } = $props();

  const { chat } = useDaemon();
  // MCP servers that come with a web page, shown in an iframe (routes/pages/[name]).
  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const pages = $derived((servers.data ?? []).filter((s) => s.page && s.enabled));

  type Add = { label: string; run: () => Promise<void> };

  async function newConversation(): Promise<void> {
    await chat.startNew();
    await goto(resolve("/conversations/open"));
  }

  // The devices page opens a pairing code when it sees ?pair.
  async function pairBrowser(): Promise<void> {
    await goto(`${resolve("/devices")}?pair`);
  }

  // The MCP servers page opens the Install dialog when it sees ?install.
  async function installExtra(): Promise<void> {
    await goto(`${resolve("/mcp")}?install`);
  }

  const NAV: { href: string; label: string; Icon: typeof Plus; add?: Add }[] = [
    { href: resolve("/sessions"), label: "Active sessions", Icon: MonitorSmartphone },
    {
      href: resolve("/conversations"),
      label: "Conversations",
      Icon: MessagesSquare,
      add: { label: "New conversation", run: newConversation },
    },
    { href: resolve("/memory"), label: "About you", Icon: UserRound },
    { href: resolve("/jobs"), label: "Jobs", Icon: CalendarClock },
    { href: resolve("/skills"), label: "Skills", Icon: WandSparkles },
    {
      href: resolve("/mcp"),
      label: "MCP servers",
      Icon: Blocks,
      add: { label: "Install a plugin", run: installExtra },
    },
    { href: resolve("/plugins"), label: "Plugins", Icon: Puzzle },
    { href: resolve("/usage"), label: "Usage", Icon: ChartColumn },
    { href: resolve("/devices"), label: "Devices", Icon: Laptop, add: { label: "Pair a browser", run: pairBrowser } },
    { href: resolve("/settings"), label: "Settings", Icon: Settings },
  ];
  const NEXT_THEME: Record<ThemePreference, ThemePreference> = { dark: "light", light: "system", system: "dark" };
  const THEME_LABEL: Record<ThemePreference, string> = { dark: "Dark", light: "Light", system: "System" };
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
      {@const active = page.url.pathname.startsWith(item.href)}
      <div class="nav-row">
        <a href={item.href} class="nav-item" aria-current={active ? "page" : undefined} title={item.label}>
          <item.Icon size={20} />
          <span class="label">{item.label}</span>
        </a>
        {#if item.add}
          {@const add = item.add}
          <button class="add" aria-label={add.label} title={add.label} onclick={() => add.run()}>
            <Plus size={16} />
          </button>
        {/if}
      </div>
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
  <div class="footer">
    <button class="nav-item" title="Theme" onclick={() => theme.set(NEXT_THEME[theme.preference])}>
      <SunMoon size={20} />
      <span class="label">Theme: {THEME_LABEL[theme.preference]}</span>
    </button>
  </div>
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
  .footer {
    margin-top: auto;
    padding: 12px 8px;
    border-top: 1px solid var(--color-border);
  }
  .footer .nav-item {
    width: 100%;
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
    .add {
      display: none;
    }
    .nav-item {
      justify-content: center;
      padding: 10px 0;
    }
  }
</style>
