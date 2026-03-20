import type { PlayModeDefinition } from './types'

export const PLAY_MODE_SCHEMA_VERSION = '1.0.0'

export const PLAY_MODE_REGISTRY: Record<string, PlayModeDefinition> = {
  'daily-challenge': {
    id: 'daily-challenge',
    label: 'Daily Challenge',
    promptNamespace: 'challenge',
    historyKinds: ['summary_snapshot'],
    endingGrades: ['normal'],
    lifecycle: {
      supportsPause: false,
      supportsResume: false,
      supportsAbandon: true,
    },
  },
  'story-lite': {
    id: 'story-lite',
    label: 'Story Lite',
    promptNamespace: 'story-lite',
    historyKinds: ['story_turn', 'special_event', 'summary_snapshot'],
    endingGrades: ['failure', 'normal', 'hidden', 'optimal'],
    lifecycle: {
      supportsPause: true,
      supportsResume: true,
      supportsAbandon: true,
    },
  },
  'story-live': {
    id: 'story-live',
    label: 'Story Live',
    promptNamespace: 'story-live',
    historyKinds: ['story_turn', 'summary_snapshot'],
    endingGrades: ['failure', 'normal', 'hidden', 'optimal'],
    lifecycle: {
      supportsPause: true,
      supportsResume: true,
      supportsAbandon: true,
    },
  },
  'turtle-soup': {
    id: 'turtle-soup',
    label: 'Turtle Soup',
    promptNamespace: 'turtle-soup',
    historyKinds: ['question_round', 'special_event', 'summary_snapshot'],
    endingGrades: ['failure', 'normal', 'hidden', 'optimal'],
    lifecycle: {
      supportsPause: true,
      supportsResume: true,
      supportsAbandon: true,
    },
  },
  'case-reconstruction': {
    id: 'case-reconstruction',
    label: 'Case Reconstruction',
    promptNamespace: 'case-reconstruction',
    historyKinds: ['investigation_turn', 'special_event', 'summary_snapshot'],
    endingGrades: ['failure', 'normal', 'hidden', 'optimal'],
    lifecycle: {
      supportsPause: true,
      supportsResume: true,
      supportsAbandon: true,
    },
  },
  'multi-life': {
    id: 'multi-life',
    label: '多重人生',
    promptNamespace: 'multi-life',
    historyKinds: ['ml_round', 'summary_snapshot'],
    endingGrades: ['normal'],
    lifecycle: {
      supportsPause: true,
      supportsResume: true,
      supportsAbandon: true,
    },
  },
}

export function getPlayModeDefinition(modeId: string) {
  return PLAY_MODE_REGISTRY[modeId]
}

export function listPlayModes() {
  return Object.values(PLAY_MODE_REGISTRY)
}
