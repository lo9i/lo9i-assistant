<script lang="ts">
  import { useDaemon } from "$lib/daemon.svelte";
  import { parsePairs } from "$lib/mcp";
  import { describe } from "$lib/notices";
  import Modal from "../Modal.svelte";

  type Props = { server: string; kind: "env" | "headers"; onclose: () => void };
  let { server, kind, onclose }: Props = $props();
  const { client } = useDaemon();
  let text = $state("");
  let error = $state("");
  const isEnv = $derived(kind === "env");

  async function save(): Promise<void> {
    try {
      const pairs = parsePairs(text, isEnv ? "=" : ":");
      await client.mcp.change(server, isEnv ? { env: pairs } : { headers: pairs });
      onclose();
    } catch (e) {
      error = describe(e);
    }
  }
</script>

<Modal
  title={isEnv ? `Environment of ${server}` : `Headers of ${server}`}
  description="Replaces all of them. The server reconnects with the new values."
  {onclose}
>
  <textarea
    class="input"
    rows="4"
    bind:value={text}
    placeholder={isEnv ? "API_KEY=…" : "Authorization: Bearer …"}
    aria-label={isEnv ? "Environment" : "Headers"}
    autocomplete="off"
    spellcheck="false"></textarea>
  <p class="text-caption">{isEnv ? "KEY=value" : "Name: value"}, one per line. Leave it empty to remove them all.</p>
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={onclose}>Cancel</button>
    <button class="btn btn--primary" onclick={save}>Save</button>
  {/snippet}
</Modal>

<style>
  textarea {
    resize: vertical;
    font-family: var(--font-mono);
  }
  textarea:not(:focus) {
    -webkit-text-security: disc;
  }
  p {
    margin: 0;
  }
</style>
