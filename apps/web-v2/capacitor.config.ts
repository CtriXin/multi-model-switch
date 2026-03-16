import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.mms.polyminder',
  appName: 'MMS',
  webDir: 'dist',
  server: {
    // Dev only: load from Vite dev server
    // url: 'http://192.168.x.x:5188',
    // cleartext: true,
  },
  ios: {
    contentInset: 'always',
    preferredContentMode: 'mobile',
    scheme: 'capacitor',
  },
}

export default config
