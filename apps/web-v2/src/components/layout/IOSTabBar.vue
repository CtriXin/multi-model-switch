<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { MessageSquare, GitMerge } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

const tabs = [
  { path: '/chat', label: '对话', icon: MessageSquare },
  { path: '/discuss', label: '讨论', icon: GitMerge },
]
</script>

<template>
  <nav class="glass-strong border-t border-border-subtle pb-[env(safe-area-inset-bottom)]">
    <div class="flex items-center justify-around h-12">
      <button
        v-for="tab in tabs"
        :key="tab.path"
        @click="router.push(tab.path)"
        class="flex flex-col items-center gap-0.5 px-6 py-1 transition-colors"
        :class="route.path === tab.path ? 'text-accent' : 'text-text-tertiary'"
      >
        <component :is="tab.icon" :size="20" :stroke-width="route.path === tab.path ? 2 : 1.5" />
        <span class="text-[10px]">{{ tab.label }}</span>
      </button>
    </div>
  </nav>
</template>
