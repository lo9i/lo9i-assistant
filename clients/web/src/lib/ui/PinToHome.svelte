<script lang="ts">
  import Pin from "@lucide/svelte/icons/pin";
  import PinOff from "@lucide/svelte/icons/pin-off";
  import { t } from "$lib/i18n.svelte";

  type Props = {
    pinned: boolean;
    ontoggle: () => void;
    /** With its label beside the icon, for an action row; an icon button otherwise. */
    labeled?: boolean;
    /** The button's look (`btn--ghost btn--icon`, `btn--neutral btn--sm`). */
    variant?: string;
  };
  let { pinned, ontoggle, labeled = false, variant = "btn--ghost btn--icon" }: Props = $props();
  const label = $derived(pinned ? t("pins.unpin") : t("pins.pin"));
</script>

<button class="btn {variant}" class:on={pinned} aria-pressed={pinned} aria-label={label} title={label} onclick={ontoggle}>
  {#if pinned}<PinOff size={14} />{:else}<Pin size={14} />{/if}{#if labeled}<span>{label}</span>{/if}
</button>

<style>
  .on {
    color: var(--color-text-primary);
  }
</style>
