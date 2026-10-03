<script lang="ts">
  import SkillsList from "$lib/ui/SkillsList.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import SettingsTabs from "$lib/ui/settings/SettingsTabs.svelte";
</script>

<!-- A settings tab of its own page. Skills from the extras are installed in Settings → Plugins. -->
<TopBar title="Settings" />

<div class="shell">
  <SettingsTabs active="skills" />
  <SkillsList />
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 16px 16px 40px;
    max-width: 1600px;
    margin: 0 auto;
  }
</style>
