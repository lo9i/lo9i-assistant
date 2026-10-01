<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import CalendarClock from "@lucide/svelte/icons/calendar-clock";
  import ChartColumn from "@lucide/svelte/icons/chart-column";
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import MessagesSquare from "@lucide/svelte/icons/messages-square";
  import MonitorSmartphone from "@lucide/svelte/icons/monitor-smartphone";
  import Settings from "@lucide/svelte/icons/settings";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import SunMoon from "@lucide/svelte/icons/sun-moon";
  import WandSparkles from "@lucide/svelte/icons/wand-sparkles";
  import { sidebar } from "$lib/sidebar.svelte";
  import { theme, type ThemePreference } from "$lib/theme.svelte";

  let { name }: { name: string } = $props();

  const NAV = [
    { href: resolve("/sessions"), label: "Active sessions", Icon: MonitorSmartphone },
    { href: resolve("/conversations"), label: "Conversations", Icon: MessagesSquare },
    { href: resolve("/jobs"), label: "Jobs", Icon: CalendarClock },
    { href: resolve("/skills"), label: "Skills", Icon: WandSparkles },
    { href: resolve("/usage"), label: "Usage", Icon: ChartColumn },
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
      <a href={item.href} class="nav-item" aria-current={active ? "page" : undefined} title={item.label}>
        <item.Icon size={20} />
        <span class="label">{item.label}</span>
      </a>
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
    background:
      linear-gradient(
        160deg,
        color-mix(in srgb, var(--glow) 13%, transparent) 0%,
        color-mix(in srgb, #ffc42e 5%, transparent) 38%,
        transparent 72%
      ),
      var(--color-bg-page);
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
  @media (max-width: 680px) {
    .label,
    .mark,
    .collapse {
      display: none;
    }
    .nav-item {
      justify-content: center;
      padding: 10px 0;
    }
  }
</style>
