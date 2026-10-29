<script lang="ts">
  import { useDaemon } from "$lib/daemon.svelte";
  import { parsePairs } from "$lib/mcp";
  import { t } from "$lib/i18n.svelte";
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

<Modal title={isEnv ? t("mcpAdd.envOf", { server }) : t("mcpAdd.headersOf", { server })} description={t("mcpAdd.replaces")} {onclose}>
  <textarea
    class="input"
    rows="4"
    bind:value={text}
    placeholder={isEnv ? "API_KEY=…" : "Authorization: Bearer …"}
    aria-label={isEnv ? t("mcpAdd.environmentLabel") : t("mcpAdd.headersLabel")}
    autocomplete="off"
    spellcheck="false"></textarea>
  <p class="text-caption">{isEnv ? t("mcpAdd.envLines") : t("mcpAdd.headerLines")}</p>
  {#if error}<p class="error-text">{error}</p>{/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={onclose}>{t("common.cancel")}</button>
    <button class="btn btn--primary" onclick={save}>{t("common.save")}</button>
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
