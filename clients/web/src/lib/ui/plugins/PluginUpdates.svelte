<script lang="ts">
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import { type Plugin, keyOf, kindOf } from "$lib/plugins";

  // Installed plugins with a newer version in the extras: update the ones picked, or all of them.
  type Props = { plugins: Plugin[]; busy: boolean; onupdate: (picked: Plugin[]) => Promise<void> };
  let { plugins, busy, onupdate }: Props = $props();
  // Every plugin starts picked; unpicking one leaves it at its version.
  let skipped = $state(new Set<string>());
  const picked = $derived(plugins.filter((p) => !skipped.has(keyOf(p))));
  const all = $derived(picked.length === plugins.length);

  function toggle(p: Plugin, on: boolean): void {
    const next = new Set(skipped);
    if (on) next.delete(keyOf(p));
    else next.add(keyOf(p));
    skipped = next;
  }

  function toggleAll(on: boolean): void {
    skipped = on ? new Set() : new Set(plugins.map(keyOf));
  }

  function versions(p: Plugin): [string, string] {
    const found = p.kind === "server" ? p.server : p.skill;
    return [found.installed_version || "–", found.version ?? ""];
  }
</script>

<section class="table-card surface--glass updates">
  <header class="toolbar">
    <div>
      <h2 class="text-heading">Updates</h2>
      <p class="text-meta">Newer versions in the extras. Uncheck the ones to leave as they are.</p>
    </div>
    <div class="tools">
      <span class="pill">{plugins.length}</span>
      <button class="btn btn--neutral btn--sm" disabled={busy || !picked.length || all} onclick={() => onupdate(picked)}
        >Update selected ({picked.length})</button
      >
      <button class="btn btn--primary btn--sm" disabled={busy} onclick={() => onupdate(plugins)}><RefreshCw size={14} />Update all</button>
    </div>
  </header>
  <table class="data-table">
    <thead>
      <tr>
        <th class="check"
          ><input type="checkbox" aria-label="Pick all" checked={all} onchange={(e) => toggleAll(e.currentTarget.checked)} /></th
        >
        <th>Plugin</th>
        <th class="hide-narrow">Kind</th>
        <th>Installed</th>
        <th>New</th>
      </tr>
    </thead>
    <tbody>
      {#each plugins as p (keyOf(p))}
        {@const [installed, available] = versions(p)}
        <tr>
          <td class="check"
            ><input
              type="checkbox"
              aria-label="Update {p.name}"
              checked={!skipped.has(keyOf(p))}
              onchange={(e) => toggle(p, e.currentTarget.checked)}
            /></td
          >
          <td>{p.name}</td>
          <td class="hide-narrow">{kindOf(p)}</td>
          <td>{installed}</td>
          <td><strong>{available}</strong></td>
        </tr>
      {/each}
    </tbody>
  </table>
</section>

<style>
  .updates {
    flex: none;
    overflow: hidden;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
    padding: 16px 24px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .tools {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .check {
    width: 36px;
  }
  .check input {
    cursor: pointer;
  }
</style>
