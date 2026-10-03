<script lang="ts">
  import Download from "@lucide/svelte/icons/download";
  import { useDaemon } from "$lib/daemon.svelte";
  import InstallDialog from "$lib/ui/repositories/InstallDialog.svelte";
  import SkillsList from "$lib/ui/SkillsList.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { notices } = useDaemon();
  let installing = $state(false);
</script>

<TopBar title="Skills">
  {#snippet actions()}
    <button class="btn btn--primary" onclick={() => (installing = true)}><Download size={16} /><span class="hide-narrow">Install</span></button>
  {/snippet}
</TopBar>

<div class="shell"><SkillsList /></div>

{#if installing}
  <InstallDialog
    kind="skill"
    onclose={(installed) => {
      installing = false;
      if (installed) notices.notify(`Installed ${installed.join(", ")}. The assistant uses them from your next message.`);
    }}
  />
{/if}

<style>
  .shell {
    padding: 16px 16px 40px;
    max-width: 1600px;
    margin: 0 auto;
  }
</style>
