import { Capacitor } from '@capacitor/core'

export async function shareText(title: string, text: string) {
  if (Capacitor.isNativePlatform()) {
    const { Share } = await import('@capacitor/share')
    await Share.share({ title, text, dialogTitle: title })
  } else {
    if (navigator.share) {
      await navigator.share({ title, text })
    } else {
      await navigator.clipboard.writeText(text)
    }
  }
}
