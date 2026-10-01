<script lang="ts">
  import UsageReport from "$lib/ui/UsageReport.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
</script>

<TopBar title="Usage" />

<div class="shell"><UsageReport /></div>

<style>
  .shell {
    padding: 16px 16px 40px;
    max-width: 1600px;
    margin: 0 auto;
  }
</style>
