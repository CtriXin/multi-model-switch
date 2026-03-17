import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/SetupGuide.vue'),
    meta: { title: '首页', icon: 'house' },
  },
  {
    path: '/setup',
    name: 'setup',
    redirect: () => '/',
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
    meta: { title: '辩论', icon: 'git-merge' },
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
  {
    path: '/v3/design',
    name: 'design-v3',
    component: () => import('@/views/DesignSystemV2.vue'),
    meta: { title: 'V3 电影级设计系统', icon: 'sparkles' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
