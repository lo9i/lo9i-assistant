<script lang="ts">
  import { tick } from "svelte";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import ScrollText from "@lucide/svelte/icons/scroll-text";
  import { isAbort } from "$lib/api/errors";
  import type { LogEntry, LogFileInfo, LogQuery } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { ALL, DEFAULT_LINES, LINES, applyLogEvent, fileSize, levelLabel, logLine, tone } from "$lib/logs";
  import { describe } from "$lib/notices";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import Toggle from "$lib/ui/Toggle.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { client } = useDaemon();
  // The files, levels and components to pick from don't change while the daemon runs.
  const options = resource((c) => c.logs.options(), []);

  let file = $state("daemon");
  let level = $state(ALL);
  let component = $state(ALL);
  let lines = $state(DEFAULT_LINES);
  // Auto-refresh follows the log over the daemon's event stream, not a timer.
  let follow = $state(false);
  // Bumped by the refresh button, so the effect below loads again.
  let refreshes = $state(0);

  let shown = $state<LogFileInfo>();
  let entries = $state<LogEntry[]>([]);
  let error = $state<string | null>(null);
  let loading = $state(false);
  let body = $state<HTMLElement>();
  // Whether the newest line is in view; new lines keep it there, but don't pull a reader back down.
  let atBottom = true;

  const query = $derived<LogQuery>({ level, component, lines });

  $effect(() => {
    void refreshes;
    const controller = new AbortController();
    if (follow) void followLog(file, query, controller.signal);
    else void loadPage(file, query, controller.signal);
    return () => controller.abort();
  });

  async function loadPage(name: string, q: LogQuery, signal: AbortSignal): Promise<void> {
    loading = true;
    try {
      const page = await client.logs.page(name, q);
      if (signal.aborted) return;
      await show(page.file, page.entries, true);
    } catch (e) {
      if (!signal.aborted) error = describe(e);
    } finally {
      if (!signal.aborted) loading = false;
    }
  }

  async function followLog(name: string, q: LogQuery, signal: AbortSignal): Promise<void> {
    loading = true;
    try {
      for await (const event of client.logs.follow(name, q, signal)) {
        loading = false;
        const page = event.kind === "page";
        await show(page ? event.page.file : shown, applyLogEvent(entries, event, q.lines), page);
      }
    } catch (e) {
      if (!isAbort(e)) error = describe(e);
    }
  }

  async function show(info: LogFileInfo | undefined, next: LogEntry[], fresh: boolean): Promise<void> {
    shown = info;
    entries = next;
    error = null;
    if (!fresh && !atBottom) return;
    await tick();
    body?.scrollTo({ top: body.scrollHeight });
  }

  function scrolled(): void {
    if (body) atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 24;
  }

  const fileName = $derived(shown?.file_name ?? options.data?.files.find((f) => f.name === file)?.file_name ?? `${file}.log`);
</script>

{#snippet row(label: string, values: { id: string; label: string }[], current: string, pick: (id: string) => void)}
  <div class="filter">
    <span class="micro-label">{label}</span>
    <div class="tabs" role="radiogroup" aria-label={label}>
      {#each values as v (v.id)}
        <button role="radio" aria-checked={v.id === current} class:active={v.id === current} onclick={() => pick(v.id)}>
          {v.label}
        </button>
      {/each}
    </div>
  </div>
{/snippet}

<TopBar title="Logs">
  {#snippet actions()}
    <label class="follow">
      <span class="micro-label">Auto-refresh</span>
      <Toggle checked={follow} label="Auto-refresh: follow the log live" onchange={(on) => (follow = on)} />
    </label>
    <button class="btn btn--outline" onclick={() => refreshes++} disabled={loading} title="Load the log again">
      <RefreshCw size={16} />
      <span class="hide-narrow">Refresh</span>
    </button>
  {/snippet}
</TopBar>

<div class="shell">
  <section class="filters surface--glass" aria-label="Filters">
    {#if options.error}
      <p class="error-text">{options.error}</p>
    {:else if options.data}
      {@const o = options.data}
      {@render row(
        "File",
        o.files.map((f) => ({ id: f.name, label: f.file_name })),
        file,
        (id) => (file = id),
      )}
      {@render row(
        "Level",
        [{ id: ALL, label: "All" }, ...o.levels.map((l) => ({ id: l, label: levelLabel(l) }))],
        level,
        (id) => (level = id),
      )}
      {@render row(
        "Component",
        [{ id: ALL, label: "All" }, ...o.components.map((c) => ({ id: c, label: c }))],
        component,
        (id) => (component = id),
      )}
      {@render row(
        "Lines",
        LINES.map((n) => ({ id: String(n), label: String(n) })),
        String(lines),
        (id) => (lines = Number(id)),
      )}
    {/if}
  </section>

  <section class="log surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="file">{fileName}</h2>
        <p class="text-meta">
          {options.data?.files.find((f) => f.name === file)?.description ?? ""}
          {#if level !== ALL}At {levelLabel(level).toLowerCase()} or above.{/if}
          {#if follow}Following live.{/if}
        </p>
      </div>
      {#if shown}<span class="pill" title={shown.path}>{fileSize(shown.size)}</span>{/if}
    </header>
    {#if error}
      <p class="error-text pad">{error}</p>
    {:else if entries.length === 0 && !loading}
      <EmptyState icon={ScrollText} title="Nothing here" text="Nothing logged matches these filters." />
    {:else}
      <div class="lines" bind:this={body} onscroll={scrolled} role="log" aria-live={follow ? "polite" : "off"}>
        {#each entries as entry, i (i)}
          <div class="line {tone(entry.level)}">{logLine(entry)}</div>
        {/each}
      </div>
    {/if}
  </section>
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
  .follow {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }
  .filters {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px 24px;
  }
  .filter {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }
  .filter .micro-label {
    width: 96px;
    flex: none;
  }
  .filter .tabs {
    flex-wrap: wrap;
  }
  .log {
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 16px 24px;
    min-height: 66px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .file {
    margin: 0;
    font-family: var(--font-mono);
    font-size: var(--font-size-md);
    font-weight: 600;
  }
  .pad {
    padding: 24px;
  }
  .lines {
    max-height: calc(100dvh - 420px);
    min-height: 240px;
    overflow-y: auto;
    padding: 12px 0;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    line-height: 1.6;
  }
  .line {
    padding: 1px 24px;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    color: var(--color-text-muted);
  }
  .line.warn {
    color: var(--color-warn);
    background: color-mix(in srgb, var(--color-warn) 8%, transparent);
  }
  .line.danger {
    color: var(--color-danger);
    background: color-mix(in srgb, var(--color-danger) 9%, transparent);
  }
  @media (max-width: 680px) {
    .filter {
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
    }
    .toolbar {
      padding: 12px 16px;
    }
    .filters {
      padding: 12px 16px;
    }
    .line {
      padding: 1px 16px;
    }
    .lines {
      max-height: none;
    }
  }
</style>
