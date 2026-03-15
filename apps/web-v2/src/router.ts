import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/chat',
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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
