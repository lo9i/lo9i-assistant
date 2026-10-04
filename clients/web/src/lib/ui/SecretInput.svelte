<script lang="ts">
  import Eye from "@lucide/svelte/icons/eye";
  import EyeOff from "@lucide/svelte/icons/eye-off";

  // A secret field (an API key, a token) with a button that shows what was typed, to check it.
  // No fallback for `value`: a form's field not filled in yet binds undefined, which Svelte refuses
  // for a bindable prop with a default.
  type Props = { value: string | undefined; label: string; placeholder?: string; required?: boolean; onchange?: () => void };
  let { value = $bindable(), label, placeholder = "", required = false, onchange }: Props = $props();
  let shown = $state(false);
</script>

<div class="secret">
  <input
    class="input"
    type={shown ? "text" : "password"}
    autocomplete="off"
    spellcheck="false"
    {placeholder}
    aria-label={label}
    bind:value
    {required}
    {onchange}
  />
  <button
    type="button"
    class="btn btn--icon reveal"
    style="--btn-icon-size: 32px"
    aria-label={shown ? `Hide ${label}` : `Show ${label}`}
    title={shown ? "Hide" : "Show"}
    aria-pressed={shown}
    onclick={() => (shown = !shown)}
  >
    {#if shown}<EyeOff size={16} />{:else}<Eye size={16} />{/if}
  </button>
</div>

<style>
  .secret {
    position: relative;
    display: flex;
  }
  .secret .input {
    flex: 1;
    padding-right: 40px;
  }
  .reveal {
    position: absolute;
    right: 4px;
    top: 50%;
    transform: translateY(-50%);
  }
</style>
