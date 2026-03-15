/**
 * MMS Contracts - Shared type definitions for Web App
 * 前后端共享的契约定义
 */

// ============================================================================
// Model Types - 模型相关类型
// ============================================================================

/** 模型价格等级: 0=经济, 1=主力, 2=旗舰 */
export type ModelTier = 0 | 1 | 2;

/** 模型分类 */
export type ModelCategory =
  | 'Claude'
  | 'OpenAI'
  | 'Google'
  | '国产'
  | 'DeepSeek'
  | 'Other';

/** 模型标签 */
export type ModelTag = 'fast' | 'reasoning' | 'recommended' | 'vision' | 'coding';

/** Provider 类型 */
export type ProviderType = 'anthropic' | 'openai' | 'google' | 'deepseek' | 'moonshot' | 'gateway';

/** 模型元数据 */
export interface ModelMeta {
  /** 模型ID，如 "claude-sonnet-4-6" */
  id: string;
  /** 显示名称 */
  name: string;
  /** Provider */
  provider: ProviderType;
  /** 分类 */
  category: ModelCategory;
  /** 价格Tier */
  tier: ModelTier;
  /** 输入价格 $/M tokens */
  priceInput: number;
  /** 输出价格 $/M tokens */
  priceOutput: number;
  /** 标签 */
  tags: ModelTag[];
  /** 上下文长度 */
  contextWindow: number;
  /** 是否已选中 */
  selected?: boolean;
  /** 是否已收藏 */
  favorited?: boolean;
}

/** 预设方案 */
export interface Preset {
  id: string;
  name: string;
  models: string[];
  builtin: boolean;
  icon?: string;
}

// ============================================================================
// Provider & Account Types
// ============================================================================

/** Provider 配置 */
export interface ProviderConfig {
  id: ProviderType;
  name: string;
  enabled: boolean;
  hasOAuth: boolean;
  hasApiKey: boolean;
  baseUrl?: string;
}

/** Account 信息 */
export interface AccountInfo {
  id: string;
  provider: ProviderType;
  name: string;
  email?: string;
  avatar?: string;
  isActive: boolean;
}

// ============================================================================
// Session Types - 会话相关
// ============================================================================

/** 应用模式 */
export type AppMode = 'chat' | 'discuss';

/** Session 状态 */
export interface Session {
  id: string;
  mode: AppMode;
  title: string;
  models: string[];
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  isArchived?: boolean;
}

/** Brief 结构 - 从响应中提取的摘要 */
export interface Brief {
  approach: string;
  reasoning: string;
  risks: string[];
  keyDecisions: string[];
  nextStep: string;
}

// ============================================================================
// Chat Types - 聊天模式
// ============================================================================

/** 响应状态 */
export type ResponseStatus = 'idle' | 'loading' | 'streaming' | 'done' | 'error' | 'cancelled';

/** Chat 消息 */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  model?: string;
  timestamp: string;
  attachments?: Attachment[];
}

/** Chat 单模型响应 */
export interface ChatResponse {
  model: string;
  content: string;
  displayText: string;
  brief: Brief | null;
  elapsed: number;
  status: ResponseStatus;
  error?: string;
  timestamp: string;
}

/** 一轮对话 */
export interface ChatRound {
  id: string;
  prompt: string;
  responses: ChatResponse[];
  selectedModel?: string;
  timestamp: string;
  attachments?: Attachment[];
}

/** Chat Session 完整状态 */
export interface ChatSessionState {
  id: string;
  rounds: ChatRound[];
  selectedModels: string[];
  isActive: boolean;
}

// ============================================================================
// Discuss Types - 讨论模式
// ============================================================================

/** Discuss 阶段 */
export type DiscussPhase = 1 | 2 | 3;

/** 阶段状态 */
export type PhaseStatus = 'waiting' | 'running' | 'completed';

/** Phase 1: 单模型方案摘要 */
export interface Phase1Summary {
  model: string;
  ok: boolean;
  brief?: Brief;
  content?: string;
  error?: string;
  elapsed: number;
}

/** Phase 2: 交叉审查 */
export interface Phase2Review {
  reviewer: string;
  target: string;
  ok: boolean;
  agreement?: string;
  challenge?: string;
  betterOption?: string;
  error?: string;
  skipped?: boolean;
}

/** Phase 3: 综合结论 */
export interface Phase3Synthesis {
  synthesizer: string;
  content: string;
  elapsed: number;
}

/** Discuss Session 完整状态 */
export interface DiscussSessionState {
  id: string;
  prompt: string;
  models: string[];
  phase: DiscussPhase;
  phaseStatus: PhaseStatus;
  phase1Summaries: Phase1Summary[];
  phase2Reviews: Phase2Review[];
  phase3Synthesis: Phase3Synthesis | null;
  synthesizer?: string;
  isActive: boolean;
  createdAt: string;
}

// ============================================================================
// API Request/Response Types
// ============================================================================

/** Chat 请求 */
export interface ChatRequest {
  models: string[];
  prompt: string;
  sessionId?: string;
  images?: string[];
}

/** Discuss 请求 */
export interface DiscussRequest {
  models: string[];
  prompt: string;
  cross?: boolean;
  sessionId?: string;
}

/** SSE 事件类型 */
export interface SSEEvent<T = unknown> {
  type: string;
  data: T;
}

/** Chat SSE 事件 */
export interface ChatChunkEvent {
  model: string;
  text: string;
}

export interface ChatModelDoneEvent {
  model: string;
  elapsed: number;
  status: ResponseStatus;
  error?: string;
}

/** Discuss SSE 事件 */
export interface DiscussPhaseStartEvent {
  phase: DiscussPhase;
  name: string;
  total: number;
  synthesizer?: string;
}

export interface DiscussPhase1CompleteEvent {
  summaries: Phase1Summary[];
}

export interface DiscussPhase2CompleteEvent {
  reviews: Phase2Review[];
}

export interface DiscussPhase3ChunkEvent {
  text: string;
}

export interface DiscussCompleteEvent {
  synthesizer: string;
  final: string;
}

// ============================================================================
// Bootstrap Types
// ============================================================================

/** Bootstrap 配置 */
export interface BootstrapConfig {
  version: string;
  features: string[];
  providers: ProviderConfig[];
  accounts: AccountInfo[];
  presets: Preset[];
  limits: {
    maxModels: number;
    minModelsChat: number;
    minModelsDiscuss: number;
  };
}

// ============================================================================
// UI Types
// ============================================================================

/** 附件 */
export interface Attachment {
  id: string;
  type: 'image' | 'file';
  name: string;
  size: number;
  url: string;
  mimeType: string;
}

/** Toast 通知 */
export interface ToastMessage {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  message: string;
  duration?: number;
}

// ============================================================================
// Constants
// ============================================================================

/** 最大选择模型数 */
export const MAX_SELECT = 5;

/** Chat 最少选择数 */
export const MIN_SELECT_CHAT = 2;

/** Discuss 最少选择数 */
export const MIN_SELECT_DISCUSS = 2;

/** Tier 颜色映射 */
export const TIER_COLORS: Record<ModelTier, string> = {
  0: '#10B981', // emerald-500 - 经济
  1: '#3B82F6', // blue-500 - 主力
  2: '#F59E0B', // amber-500 - 旗舰
};

/** Tier 名称映射 */
export const TIER_NAMES: Record<ModelTier, string> = {
  0: '经济',
  1: '主力',
  2: '旗舰',
};

/** 分类显示名称 */
export const CATEGORY_NAMES: Record<ModelCategory, string> = {
  'Claude': 'Claude',
  'OpenAI': 'OpenAI',
  'Google': 'Google',
  '国产': '国产模型',
  'DeepSeek': 'DeepSeek',
  'Other': '其他',
};

/** Provider 显示名称 */
export const PROVIDER_NAMES: Record<ProviderType, string> = {
  'anthropic': 'Anthropic',
  'openai': 'OpenAI',
  'google': 'Google',
  'deepseek': 'DeepSeek',
  'moonshot': 'Moonshot',
  'gateway': 'Gateway',
};

/** 分类顺序 */
export const CATEGORY_ORDER: ModelCategory[] = [
  'Claude',
  'OpenAI',
  'Google',
  'DeepSeek',
  '国产',
  'Other',
];

// ============================================================================
// Utility Functions
// ============================================================================

/** 获取 Tier 颜色 */
export function getTierColor(tier: ModelTier): string {
  return TIER_COLORS[tier];
}

/** 获取 Tier 名称 */
export function getTierName(tier: ModelTier): string {
  return TIER_NAMES[tier];
}

/** 获取分类名称 */
export function getCategoryName(category: ModelCategory): string {
  return CATEGORY_NAMES[category];
}

/** 获取 Provider 名称 */
export function getProviderName(provider: ProviderType): string {
  return PROVIDER_NAMES[provider];
}
