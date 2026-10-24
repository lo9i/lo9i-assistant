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
    {@const h = (p.value / max) * (H - 4)}
    <rect x={i * slot + slot * 0.15} y={H - h} width={slot * 0.7} height={h} class="bar" />
    <rect x={i * slot} y="0" width={slot} height={H} fill="transparent">
      <title>{p.day}: {p.value.toLocaleString()}</title>
    </rect>
  {/each}
</svg>

<style>
  svg {
    width: 100%;
    height: 70px;
    display: block;
  }
  .bar {
    fill: #f97316;
  }
</style>
