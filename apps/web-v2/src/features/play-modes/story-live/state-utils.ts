import type { StoryLiveStoryState } from './types'

export function createInitialState(premise: string): StoryLiveStoryState {
  return {
    location: extractLocation(premise),
    characters: extractCharacters(premise),
    goals: [],
    unresolved: [],
    tension: 2,
    entities: extractEntities(premise),
    recentEvents: [],
    roundsSinceChange: 0,
    latestUserIntent: null,
    tensionHistory: [],
  }
}

export function updateStoryState(
  current: StoryLiveStoryState,
  userText: string,
  logicText: string,
  emotionText: string,
): StoryLiveStoryState {
  const prevEvents = current.recentEvents
  const newEvent = logicText.slice(0, 60)

  const mergedEvents = [...prevEvents, newEvent].slice(-3)
  const isStagnant = mergedEvents.length >= 3 && calcSimilarity(mergedEvents) > 0.7
  const changed = detectStateChange(current, userText, logicText)

  return {
    location: extractLocation(logicText) || current.location,
    characters: mergeUnique(current.characters, extractCharacters(logicText)),
    goals: mergeUnique(current.goals, extractGoals(logicText)),
    unresolved: updateUnresolved(current.unresolved, logicText),
    tension: clamp(current.tension + calculateTensionDelta(userText, emotionText), 0, 5),
    entities: mergeUnique(current.entities, extractEntities(logicText)),
    recentEvents: mergedEvents,
    roundsSinceChange: changed ? 0 : current.roundsSinceChange + 1,
    latestUserIntent: detectUserIntent(userText),
    tensionHistory: current.tensionHistory,
  }
}

/** Heuristic entity extraction via bracketed / quoted patterns */
export function extractEntities(text: string): string[] {
  const results = new Set<string>()
  const patterns = [
    /「([^」]+)」/g,
    /"([^"]+)"/g,
    /《([^》]+)》/g,
  ]
  for (const pat of patterns) {
    let m: RegExpExecArray | null
    while ((m = pat.exec(text)) !== null) {
      const entity = m[1].trim()
      if (entity.length >= 2 && entity.length <= 12) results.add(entity)
    }
  }
  return [...results]
}

export function extractCharacters(text: string): string[] {
  const results = new Set<string>()
  const patterns = [
    /[他她它]叫([^\s,，。.]{2,4})/g,
    /([^\s,，。.]{2,3})(?:说|喊|低声|冷冷|微笑着|回头)/g,
  ]
  for (const pat of patterns) {
    let m: RegExpExecArray | null
    while ((m = pat.exec(text)) !== null) {
      const name = m[1].trim()
      if (name.length >= 2 && name.length <= 4) results.add(name)
    }
  }
  return [...results]
}

export function extractGoals(text: string): string[] {
  const goals: string[] = []
  const goalPat = /(?:需要|必须|应该|要)([^。，\n]{4,20})/g
  let m: RegExpExecArray | null
  while ((m = goalPat.exec(text)) !== null) {
    goals.push(m[1].trim())
  }
  return goals.slice(0, 3)
}

export function extractLocation(text: string): string {
  const pat = /(?:在|到|从|进(?:入)?)([^，。.\n]{2,12}(?:室|房|楼|馆|街|路|巷|桥|门|口|台|层|厅|廊|角|边|外|内|中|里|上|下))/
  const m = pat.exec(text)
  return m ? m[1].trim() : ''
}

export function calculateTensionDelta(userText: string, emotionText: string): number {
  let delta = 0
  const tensionWords = ['枪', '血', '追', '逃', '死', '杀', '危险', '恐惧', '尖叫', '崩溃']
  for (const w of tensionWords) {
    if (userText.includes(w)) delta += 0.5
    if (emotionText.includes(w)) delta += 0.3
  }
  const calmWords = ['平静', '安全', '松了一口气', '笑了', '温暖']
  for (const w of calmWords) {
    if (emotionText.includes(w)) delta -= 0.3
  }
  return delta
}

export function detectUserIntent(text: string): string {
  const t = text.trim()
  if (/^(我|你|他|她|他们)/.test(t)) return 'action'
  if (/？|\?|怎么|为什么|什么|哪/.test(t)) return 'inquiry'
  return 'observe'
}

function updateUnresolved(prev: string[], logicText: string): string[] {
  const resolved = new Set<string>()
  const resolvePat = /(?:解决|查明|发现|确认|找到)([^。，\n]{2,15})/
  const m = resolvePat.exec(logicText)
  if (m) {
    const key = m[1].trim().slice(0, 8)
    for (const item of prev) {
      if (item.includes(key)) resolved.add(item)
    }
  }

  const newClues: string[] = []
  const cluePat = /(?:奇怪|不对劲|异常|可疑|没有|不见|消失)([^。，\n]{2,15})/g
  let cm: RegExpExecArray | null
  while ((cm = cluePat.exec(logicText)) !== null && newClues.length < 8) {
    newClues.push(cm[1].trim().slice(0, 12))
  }

  return [...prev.filter((u) => !resolved.has(u)), ...newClues].slice(0, 8)
}

function detectStateChange(
  current: StoryLiveStoryState,
  userText: string,
  logicText: string,
): boolean {
  const newChars = extractCharacters(logicText).filter(
    (c) => !current.characters.includes(c),
  )
  const newLoc = extractLocation(logicText)
  if (newChars.length > 0) return true
  if (newLoc && newLoc !== current.location) return true
  return Math.abs(calculateTensionDelta(userText, '')) >= 0.3
}

function mergeUnique(a: string[], b: string[]): string[] {
  const set = new Set(a)
  for (const item of b) {
    if (!set.has(item)) set.add(item)
  }
  return [...set].slice(0, 10)
}

function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val))
}

function calcSimilarity(events: string[]): number {
  if (events.length < 2) return 0

  // Strip common location/subject words to compare action content only
  const stopWords = new Set([
    '的', '了', '在', '是', '他', '她', '你', '我', '这', '那',
    '一', '个', '着', '不', '有', '到', '也', '就', '又', '被',
  ])
  const strip = (s: string) =>
    [...s].filter((ch) => !stopWords.has(ch)).join('')

  let matchCount = 0
  const base = strip(events[0])
  for (let i = 1; i < events.length; i++) {
    const other = strip(events[i])
    if (!base.length || !other.length) continue
    let shared = 0
    for (const ch of base) {
      if (other.includes(ch)) shared++
    }
    matchCount += shared / Math.max(base.length, other.length, 1)
  }
  return matchCount / Math.max(events.length - 1, 1)
}
