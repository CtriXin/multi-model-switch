import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('./views/HomeView.vue')
  },
  {
    path: '/workspace',
    name: 'workspace',
    component: () => import('./views/WorkspaceView.vue'),
    children: [
      {
        path: 'chat',
        name: 'chat',
        component: () => import('./views/ChatPane.vue')
      },
      {
        path: 'discuss',
        name: 'discuss',
        component: () => import('./views/DiscussPane.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
