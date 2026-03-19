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
    path: '/challenge',
    name: 'challenge',
    component: () => import('@/views/DailyChallengeView.vue'),
    meta: { title: '每日一辩', icon: 'flame' },
  },
  {
    path: '/story-lite',
    name: 'story-lite',
    component: () => import('@/views/StoryLiteView.vue'),
    meta: { title: '剧情冒险', icon: 'sparkles' },
  },
  {
    path: '/story-live',
    name: 'story-live',
    component: () => import('@/views/StoryLiveView.vue'),
    meta: { title: '剧情共演', icon: 'clapperboard' },
  },
  {
    path: '/case-reconstruction',
    name: 'case-reconstruction',
    component: () => import('@/views/CaseReconstructionView.vue'),
    meta: { title: '案件还原', icon: 'search' },
  },
  {
    path: '/turtle-soup',
    name: 'turtle-soup',
    component: () => import('@/views/TurtleSoupView.vue'),
    meta: { title: '海龟汤', icon: 'soup' },
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
