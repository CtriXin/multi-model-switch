// Turtle Soup — Barrel Exports

export type {
  TurtleSoupPhase,
  HostTag,
  PuzzleCategory,
  ClueDimension,
  PuzzleClue,
  PuzzleMislead,
  PuzzleHint,
  IdealPath,
  Puzzle,
  ValidationError,
  HostOutput,
  VerifierOutput,
  HintOutput,
  RecapOutput,
  QuestionRecord,
  TurtleSoupResult,
  TurtleSoupMetadata,
  TurtleSoupRecord,
} from './types'

export {
  TAG_LABELS,
  CATEGORY_LABELS,
  DIFFICULTY_LABELS,
} from './types'

export {
  MAX_ROUNDS,
  HOST_RETRY_LIMIT,
  MAX_HINTS,
  SAFE_FALLBACKS,
  pickFallback,
  PROMPT_VERSIONS,
  GENERIC_LEAK_PATTERNS,
} from './constants'

export {
  buildHostSystemPrompt,
  buildHostUserPrompt,
  buildVerifierSystemPrompt,
  buildVerifierUserPrompt,
  buildHintPrompt,
  buildRecapPrompt,
} from './prompts'

export {
  leakGuardCheck,
  type LeakGuardResult,
} from './leak-guard'

export { validatePuzzle } from './puzzles/schema'
export { SEED_PUZZLES } from './puzzles/seeds'
