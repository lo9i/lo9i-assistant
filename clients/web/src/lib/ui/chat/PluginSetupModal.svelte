<script lang="ts">
  import type { FoundServer } from "$lib/api/types";
  import { t } from "$lib/i18n.svelte";
  import Modal from "../Modal.svelte";
  import PluginSetup from "../plugins/PluginSetup.svelte";

  // An installed plugin's setup in the conversation; the run goes on when it's closed.
  let { server, ondone }: { server: FoundServer; ondone: () => void } = $props();
</script>

<Modal title={t("chat.setUp", { name: server.name })} description={server.description} width={600} onclose={ondone}>
  <PluginSetup {server} />
  {#snippet footer()}
    <button class="btn btn--primary" onclick={ondone}>{t("common.done")}</button>
  {/snippet}
</Modal>
