import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import HomeView from './views/HomeView.vue'
import ChatView from './views/ChatView.vue'
import DiscussView from './views/DiscussView.vue'
import SessionsView from './views/SessionsView.vue'
import SettingsView from './views/SettingsView.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
  },
  {
    path: '/chat',
    name: 'chat',
    component: ChatView,
  },
  {
    path: '/discuss',
    name: 'discuss',
    component: DiscussView,
  },
  {
    path: '/sessions',
    name: 'sessions',
    component: SessionsView,
  },
  {
    path: '/settings',
    name: 'settings',
    component: SettingsView,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
