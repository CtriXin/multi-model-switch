export type ExperienceMode = 'demo' | 'byok'

const EXPERIENCE_MODE_KEY = 'mms-experience-mode'

export function getExperienceMode(): ExperienceMode | null {
  const mode = localStorage.getItem(EXPERIENCE_MODE_KEY)
  if (mode === 'demo' || mode === 'byok') return mode
  return null
}

export function setExperienceMode(mode: ExperienceMode) {
  localStorage.setItem(EXPERIENCE_MODE_KEY, mode)
}

export function clearExperienceMode() {
  localStorage.removeItem(EXPERIENCE_MODE_KEY)
}
