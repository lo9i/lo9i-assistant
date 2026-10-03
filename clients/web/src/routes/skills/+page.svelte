<script lang="ts">
  import SkillsList from "$lib/ui/SkillsList.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
</script>

<!-- Skills from the extras are installed in Settings → Plugins. -->
<TopBar title="Skills" />

<div class="shell"><SkillsList /></div>

<style>
  .shell {
    padding: 16px 16px 40px;
    max-width: 1600px;
    margin: 0 auto;
  }
</style>
