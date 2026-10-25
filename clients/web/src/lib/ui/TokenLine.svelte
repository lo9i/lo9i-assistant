<script lang="ts">
  // A small line chart of one value per day, in `color` (the accent when left out).
  let {
    points,
    label,
    color = "var(--color-accent, #f59e0b)",
  }: { points: { day: string; value: number }[]; label: string; color?: string } = $props();

  const W = 300;
  const H = 70;
  const max = $derived(Math.max(1, ...points.map((p) => p.value)));
  const coords = $derived(
    points.map((p, i) => [points.length > 1 ? (i / (points.length - 1)) * W : W / 2, H - 4 - (p.value / max) * (H - 8)]),
  );
  const line = $derived(coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" "));
</script>

<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label={label} style:--line-color={color}>
  {#if coords.length}
    <polyline points={line} class="line" vector-effect="non-scaling-stroke" />
  {/if}
  {#each points as p, i (p.day)}
    <rect x={coords[i][0] - W / points.length / 2} y="0" width={W / points.length} height={H} fill="transparent">
      <title>{p.day}: {p.value.toLocaleString()}</title>
    </rect>
  {/each}
</svg>

<style>
  svg {
    width: 100%;
    height: 44px;
    display: block;
  }
  .line {
    fill: none;
    stroke: var(--line-color);
    stroke-width: 2;
    stroke-linejoin: round;
  }
</style>
