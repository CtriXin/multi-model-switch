import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'workspace',
      component: () => import('./views/WorkspaceView.vue'),
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('./views/HomePane.vue'),
        },
        {
          path: 'chat/:id?',
          name: 'chat',
          component: () => import('./views/ChatPane.vue'),
        },
        {
          path: 'discuss/:id?',
          name: 'discuss',
          component: () => import('./views/DiscussPane.vue'),
        },
        {
          path: 'models',
          name: 'models',
          component: () => import('./views/ModelsPane.vue'),
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('./views/SettingsPane.vue'),
        },
        {
          path: 'setup',
          name: 'setup',
          component: () => import('./views/SetupGuide.vue'),
        },
      ],
    },
  ],
})
