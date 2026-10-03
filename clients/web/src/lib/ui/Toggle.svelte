<script lang="ts">
  let { checked, label, onchange }: { checked: boolean; label: string; onchange: (on: boolean) => void } = $props();
</script>

<button class="toggle" role="switch" aria-checked={checked} aria-label={label} onclick={() => onchange(!checked)}>
  <span class="knob"></span>
</button>

<style>
  .toggle {
    position: relative;
    flex: none;
    width: 34px;
    height: 20px;
    border: 0;
    border-radius: var(--radius-full);
    background: color-mix(in srgb, var(--color-text-primary) 14%, transparent);
    cursor: pointer;
    transition: background 0.18s ease;
  }
  .toggle[aria-checked="true"] {
    background: var(--color-success);
  }
  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #fff;
    transition: transform 0.18s ease;
  }
  .toggle[aria-checked="true"] .knob {
    transform: translateX(14px);
  }
  .toggle:focus-visible {
    outline: 2px solid color-mix(in srgb, var(--color-accent) 55%, transparent);
    outline-offset: 2px;
  }
</style>
