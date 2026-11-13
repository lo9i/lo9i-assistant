<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { formatNumber, t } from "$lib/i18n.svelte";
  import { categoryName, cleanedTogether, cleans, diskSize, segments } from "$lib/disk";
  import { percent, shade } from "$lib/contextParts";
  import type { CleanReport, DiskCategory } from "$lib/api/types";
  import Confirm from "../Confirm.svelte";
  import SettingsCard from "../Card.svelte";

  // How much disk lo9i takes, as one bar of its categories, largest first, each listed below with its size and what
  // cleaning it frees. Clean up cleans every category but the plugins' downloads, which are the user's files and go
  // only with their own Clean. Measuring walks every folder, so it's loaded when the card shows and after a cleaning.
  const { client, notices } = useDaemon();
  const usage = resource((c) => c.disk.usage(), []);
  const shown = $derived(usage.data ? segments(usage.data.categories, usage.data.total) : []);
  const together = $derived(usage.data ? cleanedTogether(usage.data.categories) : []);
  let hovered = $state<string | null>(null);
  // Clean up (null category) or one category's Clean, waiting for the user to confirm.
  let asking = $state<{ category: DiskCategory | null } | null>(null);
  let cleaning = $state(false);

  async function clean(category: DiskCategory | null): Promise<void> {
    cleaning = true;
    try {
      const done = await client.disk.clean(category ? [category.name] : []);
      usage.data = done.usage;
      tell(done);
    } catch (e) {
      notices.report(e);
    } finally {
      cleaning = false;
    }
  }

  function tell(done: CleanReport): void {
    notices.notify(t("disk.freed", { size: diskSize(done.freed) }));
    const [first] = done.failed;
    if (first) notices.notify(t("disk.failed", { count: done.failed.length, reason: `${first.path}: ${first.reason}` }), "error");
  }

  function confirmText(category: DiskCategory | null): string {
    if (!category) return t("disk.cleanUpText");
    if (category.on_request) return t("disk.downloadsText", { size: diskSize(category.freeable) });
    return t("disk.cleanText", { what: cleans(category.name), size: diskSize(category.freeable) });
  }
</script>

<SettingsCard id="disk" title={t("disk.title")} sub={usage.data ? t("disk.sub", { home: usage.data.home }) : undefined}>
  {#snippet status()}
    <span class="pill" title={usage.data ? formatNumber(usage.data.total) : undefined}>{usage.data ? diskSize(usage.data.total) : "…"}</span
    >
  {/snippet}
  {#if usage.data === undefined}
    <p class="text-meta">{usage.error ?? t("disk.measuring")}</p>
  {:else}
    {@const data = usage.data}
    <!-- The rows below are the keyboard's and screen readers' way to the same numbers; the bar answers the pointer. -->
    <div class="bar" role="img" aria-label={t("disk.bar")}>
      {#each shown as part, rank (part.name)}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <span
          class="part"
          class:dim={hovered !== null && hovered !== part.name}
          style="flex-basis: {part.share * 100}%; background: {shade(rank, shown.length)}"
          title="{categoryName(part.name)}: {t('disk.share', { size: diskSize(part.bytes), share: percent(part.share) })}"
          onpointerenter={() => (hovered = part.name)}
          onpointerleave={() => (hovered = null)}
        ></span>
      {/each}
    </div>
    <ul class="rows">
      {#each shown as part, rank (part.name)}
        <li class:active={hovered === part.name} onpointerenter={() => (hovered = part.name)} onpointerleave={() => (hovered = null)}>
          <span class="swatch" style="background: {shade(rank, shown.length)}"></span>
          <span class="what">
            <span class="name">{categoryName(part.name)}</span>
            {#if part.freeable}
              <span class="text-meta"
                >{t("disk.toFree", { size: diskSize(part.freeable) })}<span class="cleans"> · {cleans(part.name)}</span></span
              >
            {/if}
          </span>
          <span class="size" title={formatNumber(part.bytes)}>{diskSize(part.bytes)}</span>
          <span class="share">{percent(part.share)}</span>
          <span class="action">
            {#if part.freeable}
              <button class="btn btn--ghost btn--sm" disabled={cleaning} onclick={() => (asking = { category: part })}
                >{t("disk.clean")}</button
              >
            {/if}
          </span>
        </li>
      {/each}
    </ul>
    <div class="footer">
      {#if together.length}
        <button class="btn btn--primary btn--sm" disabled={cleaning} onclick={() => (asking = { category: null })}>
          {t("disk.cleanUp", { size: diskSize(data.freeable) })}
        </button>
      {:else}
        <span class="text-meta">{t("disk.nothingToClean")}</span>
      {/if}
    </div>
  {/if}
</SettingsCard>

{#if asking && usage.data}
  {@const category = asking.category}
  <Confirm
    title={category
      ? t("disk.cleanTitle", { name: categoryName(category.name) })
      : t("disk.cleanUpTitle", { size: diskSize(usage.data.freeable) })}
    text={confirmText(category)}
    action={t("disk.clean")}
    onanswer={(yes) => {
      // Before clearing `asking`: `category` is derived from it.
      if (yes) void clean(category);
      asking = null;
    }}
  />
{/if}

<style>
  :global(#disk) {
    /* The brand's teal-gray, the largest category strongest, fading to the smallest, as the context's ring. */
    --ring-strong: #9fd3d1;
    --ring-weak: #3f5859;
  }
  :global(:root[data-theme="light"] #disk) {
    --ring-strong: #364445;
    --ring-weak: #c3dbd9;
  }
  .bar {
    display: flex;
    gap: 2px;
    height: 14px;
    border-radius: 4px;
    overflow: hidden;
    background: color-mix(in srgb, var(--color-text-primary) 5%, transparent);
  }
  .part {
    min-width: 0;
    flex-grow: 0;
    flex-shrink: 1;
    transition: opacity 120ms ease;
  }
  .part.dim {
    opacity: 0.45;
  }
  .rows {
    list-style: none;
    margin: -12px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }
  .rows li {
    display: grid;
    grid-template-columns: 10px minmax(0, 1fr) auto 3.5em 4.5em;
    align-items: center;
    gap: 10px;
    padding: 4px 8px;
    border-radius: var(--radius-sm);
    font-size: var(--font-size-sm);
  }
  .rows li.active {
    background: var(--color-bg-hover-ghost);
  }
  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 3px;
  }
  .what {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .what > span {
    overflow-wrap: anywhere;
  }
  .size,
  .share {
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .share {
    color: var(--color-text-muted);
  }
  .action {
    display: flex;
    justify-content: flex-end;
  }
  @media (max-width: 560px) {
    .rows li {
      grid-template-columns: 10px minmax(0, 1fr) auto auto;
    }
    .share,
    .cleans {
      display: none;
    }
  }
  .footer {
    display: flex;
    justify-content: flex-end;
    margin-top: -12px;
  }
</style>
