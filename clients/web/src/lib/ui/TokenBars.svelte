<script lang="ts">
  // A small bar chart of one value per day, in orange.
  let { points, label }: { points: { day: string; value: number }[]; label: string } = $props();

  const W = 300;
  const H = 70;
  const max = $derived(Math.max(1, ...points.map((p) => p.value)));
  const slot = $derived(points.length ? W / points.length : W);
</script>

<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label={label}>
  {#each points as p, i (p.day)}
    {@const h = (p.value / max) * (H - 5)}
    <rect x={i * slot + slot * 0.15} y={H - 1 - h} width={slot * 0.7} height={h} class="bar" vector-effect="non-scaling-stroke" />
    <rect x={i * slot} y="0" width={slot} height={H} fill="transparent">
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
  .bar {
    fill: color-mix(in srgb, #f97316 15%, transparent);
    stroke: #f97316;
    stroke-width: 2;
    stroke-linejoin: round;
  }
</style>
