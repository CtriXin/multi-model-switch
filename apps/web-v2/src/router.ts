import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    redirect: () => {
      // Will be handled by the navigation guard below
      return '/chat'
    },
  },
  {
    path: '/setup',
    name: 'setup',
    component: () => import('@/views/SetupGuide.vue'),
    meta: { title: '🚀 快速开始', icon: 'rocket' },
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '对话', icon: 'message-square' },
  },
  {
    path: '/discuss',
    name: 'discuss',
    component: () => import('@/views/DiscussView.vue'),
    meta: { title: '讨论', icon: 'git-merge' },
  },
  {
    path: '/advisors',
    name: 'advisors',
    component: () => import('@/views/AdvisorsView.vue'),
    meta: { title: '锦囊团', icon: 'users' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '设置', icon: 'settings' },
  },
  {
    path: '/models',
    name: 'models',
    component: () => import('@/views/ModelsView.vue'),
    meta: { title: '模型管理', icon: 'cpu' },
  },
  {
    path: '/design',
    name: 'design',
    component: () => import('@/views/DesignSystem.vue'),
    meta: { title: '设计系统', icon: 'palette' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// First-time navigation guard: redirect to /setup if no real provider is configured
let firstNavDone = false

router.beforeEach(async (to) => {
  if (firstNavDone || to.name === 'setup') return

  // Only check on the very first navigation (app load)
  if (to.path === '/' || to.name === 'home') {
    firstNavDone = true
    // Check if any non-mock provider has a key configured
    // We read from localStorage directly to avoid Pinia timing issues
    const STORAGE_KEY = 'mms-providers'
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const providers = JSON.parse(raw)
        // If user has explicitly configured providers, they might have keys
        // But we can't check IndexedDB synchronously, so we check if there are
        // any non-mock providers that the user has interacted with
        const hasNonMock = providers.some(
          (p: any) => p.type !== 'mock' && p.enabled !== false,
        )
        // For a more reliable check, also look at the DB name existence
        // But for simplicity, check if any IndexedDB keys exist via a quick probe
        const dbExists = await checkKeychainHasKeys()
        if (!dbExists) {
          return '/setup'
        }
      } else {
        // No saved providers → first time user → setup
        const dbExists = await checkKeychainHasKeys()
        if (!dbExists) {
          return '/setup'
        }
      }
    } catch {
      // On error, go to chat as fallback
    }
  }

  firstNavDone = true
})

async function checkKeychainHasKeys(): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      const req = indexedDB.open('mms-keychain', 1)
      req.onsuccess = () => {
        const db = req.result
        if (!db.objectStoreNames.contains('credentials')) {
          db.close()
          resolve(false)
          return
        }
        const tx = db.transaction('credentials', 'readonly')
        const countReq = tx.objectStore('credentials').count()
        countReq.onsuccess = () => {
          db.close()
          resolve(countReq.result > 0)
        }
        countReq.onerror = () => {
          db.close()
          resolve(false)
        }
      }
      req.onerror = () => resolve(false)
      req.onupgradeneeded = () => {
        // DB doesn't exist yet → no keys
        req.result.close()
        resolve(false)
      }
    } catch {
      resolve(false)
    }
  })
}

export default router
