<script setup lang="ts">
import { ref, computed, watchEffect, onMounted, onUnmounted } from 'vue'
import { useTheme } from '@/composables/useTheme'
import {
  Sparkles, MessageSquare, Send, Zap, Shield, Cpu,
  Layers, Palette, MousePointer2, Smartphone, Type, CheckCircle2,
  Sun, Moon, Plus, Wand2, Monitor, Layout, Download, ClipboardCheck,
  Snowflake, Flame, Ghost, Radius, Type as Typography, Grid3X3, Box,
  Eye, MousePointerClick, Target, History, Bot, GitMerge
} from 'lucide-vue-next'

const { theme, toggle: toggleTheme } = useTheme()
const activeTab = ref('overview')

// --- V3: KINETIC STATE ---
const mouseX = ref(0)
const mouseY = ref(0)
const handleMouseMove = (e: MouseEvent) => {
  mouseX.value = (e.clientX / window.innerWidth - 0.5) * 40
  mouseY.value = (e.clientY / window.innerHeight - 0.5) * 40
}
onMounted(() => window.addEventListener('mousemove', handleMouseMove))
onUnmounted(() => window.removeEventListener('mousemove', handleMouseMove))

// --- GLASS LAB STATE ---
const blurAmount = ref(25)
const saturation = ref(130)
const borderOpacity = ref(12)
const noiseOpacity = ref(6)
const showAurora = ref(true)

watchEffect(() => {
  const root = document.documentElement
  root.style.setProperty('--v3-blur', `${blurAmount.value}px`)
  root.style.setProperty('--v3-saturate', `${saturation.value}%`)
  root.style.setProperty('--v3-border-opacity', `${borderOpacity.value / 100}`)
  root.style.setProperty('--v3-noise', `${noiseOpacity.value / 100}`)
})

const glassStyle = computed(() => ({
  backdropFilter: `blur(var(--v3-blur)) saturate(var(--v3-saturate))`,
  backgroundColor: theme.value === 'dark' ? `rgba(255, 255, 255, 0.04)` : `rgba(255, 255, 255, 0.5)`,
  borderColor: theme.value === 'dark' ? `rgba(255, 255, 255, var(--v3-border-opacity))` : `rgba(0, 0, 0, 0.08)`,
}))

const sections = [
  { id: 'overview', name: '总览', icon: Sparkles },
  { id: 'spec', name: '系统规范', icon: Box },
  { id: 'lab', name: '进化实验室', icon: Wand2 },
]

const glassControls = [
  { key: 'blur', label: '模糊 (Blur)', value: blurAmount, max: 80 },
  { key: 'saturation', label: '饱和 (Saturate)', value: saturation, max: 200 },
  { key: 'border', label: '边框 (Stroke)', value: borderOpacity, max: 100 },
  { key: 'noise', label: '颗粒 (Grain)', value: noiseOpacity, max: 20 },
] as const

function updateGlassControl(key: string, value: number) {
  const target = glassControls.find(control => control.key === key)?.value
  if (target) target.value = value
}
</script>

<template>
  <div class="min-h-screen transition-all duration-1000 selection:bg-indigo-500/30 overflow-x-hidden relative"
       :class="theme === 'dark' ? 'bg-[#020205] text-white' : 'bg-[#f4f4f7] text-[#1d1d1f]'">
    
    <!-- FILM GRAIN -->
    <div class="fixed inset-0 pointer-events-none z-[100] opacity-[var(--v3-noise)] mix-blend-overlay"
         style="background-image: url('https://grainy-gradients.vercel.app/noise.svg');"></div>

    <!-- KINETIC AURORA -->
    <div v-if="showAurora" class="fixed inset-0 pointer-events-none z-0 opacity-40 dark:opacity-20"
         :style="{ transform: `translate3d(${mouseX}px, ${mouseY}px, 0)` }">
      <div class="absolute -top-[10%] -left-[10%] w-[60%] h-[60%] bg-indigo-500/30 blur-[150px] animate-blob rounded-full" />
      <div class="absolute top-[20%] -right-[10%] w-[50%] h-[50%] bg-purple-500/20 blur-[120px] animate-blob animation-delay-2000 rounded-full" />
    </div>

    <!-- Header: Cinematic V3 -->
    <header class="h-16 flex items-center justify-between px-8 sticky top-4 z-50 mx-4 md:mx-8 rounded-2xl border transition-all duration-500 shadow-2xl"
            :style="glassStyle">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-600/40">
          <Sparkles :size="16" class="text-white" />
        </div>
        <span class="font-black tracking-tighter text-xl uppercase italic">SparkRing <span class="text-indigo-600 dark:text-indigo-400">V3 SPEC</span></span>
      </div>

      <nav class="hidden lg:flex gap-1 p-1 bg-black/5 dark:bg-white/5 rounded-xl border border-white/5">
        <button v-for="s in sections" :key="s.id" @click="activeTab = s.id"
                class="px-5 py-1.5 rounded-lg text-[10px] font-black tracking-widest uppercase transition-all duration-500"
                :class="activeTab === s.id 
                  ? 'bg-indigo-600 text-white shadow-lg' 
                  : 'text-slate-500 dark:text-white/40 hover:text-indigo-600 dark:hover:text-white'">
          {{ s.name }}
        </button>
      </nav>

      <button @click="toggleTheme" class="p-2 rounded-xl hover:bg-white/10 transition-all border border-transparent hover:border-white/10">
        <Sun v-if="theme === 'dark'" :size="18" class="text-amber-400" />
        <Moon v-else :size="18" class="text-indigo-600" />
      </button>
    </header>

    <main class="relative z-10 max-w-6xl mx-auto py-24 px-6 space-y-32">
      
      <!-- HERO -->
      <section v-if="activeTab === 'overview'" class="text-center space-y-16 animate-in fade-in duration-1000">
        <div class="space-y-6">
          <div class="inline-flex items-center gap-2 px-6 py-2 rounded-full bg-indigo-600 text-white text-[10px] font-black tracking-[0.4em] uppercase shadow-2xl">
             V3 Cinematic Manifest
          </div>
          <h1 class="text-6xl md:text-[10rem] font-black tracking-tighter leading-[0.8] uppercase">
            定义<br/>像素的<br/><span class="bg-clip-text text-transparent bg-gradient-to-r from-indigo-600 via-purple-500 via-fuchsia-500 via-indigo-400 to-indigo-600 animate-gradient italic">生命。</span>
          </h1>
        </div>
        <p class="max-w-2xl mx-auto text-xl font-medium opacity-50 leading-relaxed italic">
          "A design system is not a set of rules; it is a living organism that evolves with every human touch."
        </p>
      </section>

      <!-- FULL SPECIFICATION (The comprehensive spec) -->
      <section v-if="activeTab === 'spec'" class="space-y-24 animate-in slide-in-from-bottom-10">
        
        <!-- Typography -->
        <div class="space-y-10">
          <div class="flex items-center gap-4">
             <div class="p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-600/20"><Typography :size="24" class="text-white" /></div>
             <h2 class="text-4xl font-black uppercase tracking-tighter">01. 字体排版 (Typography)</h2>
          </div>
          <div class="grid md:grid-cols-2 gap-8 p-10 rounded-[40px] border border-white/5 bg-white/5 backdrop-blur-xl">
             <div class="space-y-4 group">
                <div class="text-[10px] font-black text-indigo-500 uppercase tracking-widest border-b border-white/5 pb-2">System Meta (Labels & Nav)</div>
                <div class="text-[11px] font-black uppercase tracking-widest text-text-primary">
                   font-black uppercase tracking-widest
                </div>
                <p class="text-xs text-text-tertiary leading-relaxed">全站用于状态标签、Header操作区、侧边栏动作等所有 Meta 信息区。极高的字重配合夸张的字间距，不加任何修饰，营造极其硬核的“工业控制台”感。严格要求全大写，无一例外。</p>
             </div>
             <div class="space-y-4 group">
                <div class="text-[10px] font-black text-indigo-500 uppercase tracking-widest border-b border-white/5 pb-2">Panel Text (Menu & Commands)</div>
                <div class="text-[13px] font-black tracking-tight text-text-primary">
                   font-black tracking-tight
                </div>
                <p class="text-xs text-text-tertiary leading-relaxed">用于命令面板项或侧边栏的主层级按钮、设置项。保持极高的清晰识别度，收紧字间距，使文字更聚拢、更具点击感。</p>
             </div>
             <div class="space-y-4 group md:col-span-2">
                <div class="text-[10px] font-black text-indigo-500 uppercase tracking-widest border-b border-white/5 pb-2">Chat Content (Model Outputs)</div>
                <div class="text-sm font-medium leading-relaxed text-text-primary">
                   text-sm font-medium leading-relaxed
                </div>
                <p class="text-xs text-text-tertiary leading-relaxed">对话正文必须摒弃传统的紧凑排版。保持宽裕的行高 (leading-relaxed) 和适中字重 (font-medium)，确保即使 AI 输出万字长文，视觉上依然具有“会呼吸”的舒适性。</p>
             </div>
          </div>
        </div>

        <!-- Color System -->
        <div class="space-y-10">
          <div class="flex items-center gap-4">
             <div class="p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-600/20"><Palette :size="24" class="text-white" /></div>
             <h2 class="text-4xl font-black uppercase tracking-tighter">02. 色彩语义 (Color System)</h2>
          </div>
          <div class="grid md:grid-cols-3 gap-6 p-8 rounded-[40px] border border-white/5 bg-white/5 backdrop-blur-xl">
             <div class="p-6 rounded-3xl bg-indigo-500/10 border border-indigo-500/20 space-y-3">
                <div class="flex items-center gap-2">
                   <div class="w-4 h-4 rounded-full bg-indigo-500 shadow-lg shadow-indigo-500/50"></div>
                   <h4 class="font-black tracking-tight">Primary Accent</h4>
                </div>
                <p class="text-xs text-text-tertiary">主品牌色。用于激活的选项、提交按钮、"Spark" 品牌前缀以及高优先级的系统通知。代表稳定、智能与控制。</p>
             </div>
             <div class="p-6 rounded-3xl bg-purple-500/10 border border-purple-500/20 space-y-3">
                <div class="flex items-center gap-2">
                   <div class="w-4 h-4 rounded-full bg-purple-500 shadow-lg shadow-purple-500/50"></div>
                   <h4 class="font-black tracking-tight">Secondary Spark</h4>
                </div>
                <p class="text-xs text-text-tertiary">次级品牌色。主要用于“深度讨论(Discuss)”场景的身份标识、渐变融合区以及部分高级视觉反馈，代表思想的碰撞与发散。</p>
             </div>
             <div class="p-6 rounded-3xl bg-red-500/10 border border-red-500/20 space-y-3">
                <div class="flex items-center gap-2">
                   <div class="w-4 h-4 rounded-full bg-red-500 shadow-lg shadow-red-500/50"></div>
                   <h4 class="font-black tracking-tight">Destructive</h4>
                </div>
                <p class="text-xs text-text-tertiary">破坏性操作（如删除会话）。平态隐匿，Hover 时必须具有显式的淡红背景 (hover:bg-red-500/10) 且图标变红，确保在任何深浅模式下视觉绝对醒目。</p>
             </div>
          </div>
        </div>

        <!-- Global Layout Architecture -->
        <div class="space-y-10">
          <div class="flex items-center gap-4">
             <div class="p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-600/20"><Layout :size="24" class="text-white" /></div>
             <h2 class="text-4xl font-black uppercase tracking-tighter">03. 空间布局 (Architecture)</h2>
          </div>
          <div class="grid md:grid-cols-2 gap-8">
             <div class="p-8 rounded-[32px] border border-white/5 bg-white/5 backdrop-blur-xl space-y-4 relative overflow-hidden">
                <div class="absolute -right-10 -top-10 opacity-10"><PanelLeftOpen :size="120" /></div>
                <h3 class="text-lg font-black tracking-tighter relative z-10">Floating Sidebar (悬浮纵向胶囊)</h3>
                <p class="text-sm text-text-secondary leading-relaxed relative z-10">
                  彻底摒弃传统的“一通到底靠墙贴边”后台设计。侧边栏在 PC 端被定义为一个独立的悬浮玻璃切片 <code>(p-3, rounded-[32px])</code>。激活态一律采用高对比度反色块（纯白/纯黑），提供强烈的物理按压深度。历史记录项不再单调，必须附带色彩圆点（对话蓝/讨论紫/锦囊金）以明确功能属性。
                </p>
             </div>
             <div class="p-8 rounded-[32px] border border-white/5 bg-white/5 backdrop-blur-xl space-y-4 relative overflow-hidden">
                <div class="absolute -right-10 -top-10 opacity-10"><Box :size="120" /></div>
                <h3 class="text-lg font-black tracking-tighter relative z-10">Trinity Control Pod (三位一体对齐)</h3>
                <p class="text-sm text-text-secondary leading-relaxed relative z-10">
                  界面的控制枢纽（顶部 Header 胶囊、中部当前模型控制条、底部 Input 交互区）以及内容容器，全部强制共享统一的最大宽度约束（如 <code>max-w-6xl</code>）。从屏幕最顶端到最底部，形成一条完美的垂直中轴线。所有控件仿佛漂浮在一个隐形的玻璃轨道上。
                </p>
             </div>
          </div>
        </div>

        <!-- Chat Interface Design -->
        <div class="space-y-10">
          <div class="flex items-center gap-4">
             <div class="p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-600/20"><MessageSquare :size="24" class="text-white" /></div>
             <h2 class="text-4xl font-black uppercase tracking-tighter">04. 聊天界面 (Chat UI)</h2>
          </div>
          <div class="p-8 rounded-[40px] border border-white/5 bg-white/5 backdrop-blur-xl space-y-8">
             <div class="grid md:grid-cols-2 gap-8">
               <div class="space-y-3">
                 <h4 class="text-sm font-black uppercase tracking-widest text-indigo-400">Model Cards (瀑布流卡片)</h4>
                 <ul class="text-sm text-text-tertiary space-y-3 list-disc pl-4">
                   <li><strong class="text-white">自由生长：</strong>禁止使用 fixed height 或 <code>items-start</code> 强制拉伸。每张卡片的高度必须由内容自然决定，随流式生成自下生长。</li>
                   <li><strong class="text-white">极限滚动：</strong>必须设定阈值 <code>max-h-[clamp(360px,58vh,600px)]</code>，当文字超过此高度时，内部平滑转为滚动，避免撑爆父级结构。</li>
                   <li><strong class="text-white">对齐法则：</strong>网格模式下，同行卡片需保持视觉底线平齐，留白必须存在于底部，而非卡片内部被强制拉伸导致的空洞。</li>
                 </ul>
               </div>
               <div class="space-y-3">
                 <h4 class="text-sm font-black uppercase tracking-widest text-indigo-400">Split View (三视图不对称布局)</h4>
                 <ul class="text-sm text-text-tertiary space-y-3 list-disc pl-4">
                   <li><strong class="text-white">主从结构：</strong>当产生上下文选中时，进入“左侧 70% 主视区 + 右侧 30% 纵向缩略图”的极致工作流。</li>
                   <li><strong class="text-white">缩略图快选：</strong>右侧缩略图除提供内容预览外，必须在右上角常驻（或悬浮显示）直接勾选的 Check 按钮，允许用户无需切换视图即可将副模型直接设为新上下文。</li>
                 </ul>
               </div>
             </div>
             <div class="pt-6 border-t border-white/5">
                <h4 class="text-sm font-black uppercase tracking-widest text-indigo-400 mb-2">View Switcher (视图切换器)</h4>
                <p class="text-sm text-text-tertiary">视图模式切换（Grid/横滑/纵向）属于全局内容控制。严禁将其放入滚动的内容区或顶部的全局导航，必须将其精准锚定在对话区正上方（即“当前模型条”的最右侧）。</p>
             </div>
          </div>
        </div>

        <!-- Popovers & Overlays -->
        <div class="space-y-10">
          <div class="flex items-center gap-4">
             <div class="p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-600/20"><Layers :size="24" class="text-white" /></div>
             <h2 class="text-4xl font-black uppercase tracking-tighter">05. 浮层与弹窗 (Overlays)</h2>
          </div>
          <div class="p-8 rounded-[40px] border border-white/5 bg-white/5 backdrop-blur-xl">
             <div class="grid md:grid-cols-3 gap-6">
               <div class="space-y-2">
                 <h4 class="text-sm font-bold text-white">绝对纯色底板</h4>
                 <p class="text-[11px] text-text-tertiary leading-relaxed">
                   <strong>反直觉铁则：</strong> 弹出选择菜单（模型库、Context模式等）绝对禁止使用透明的 glass 玻璃质感。必须使用绝对不透明的纯色底（暗色: <code>#1a1a24</code>, 亮色: <code>white</code>），这是为了在浮于密集文字之上时，保证极致的阅读清晰度。
                 </p>
               </div>
               <div class="space-y-2">
                 <h4 class="text-sm font-bold text-white">嵌套圆角方程</h4>
                 <p class="text-[11px] text-text-tertiary leading-relaxed">
                   Popover 必须遵循严格的数学嵌套。外层容器使用大圆角 <code>rounded-[28px]</code> 并带有 <code>p-1.5</code> 的内衬空间；内部的交互按钮使用稍小的 <code>rounded-[20px]</code>。这确保了 Hover 时的焦点背景色能完美契合外边框的弧度，彻底根除“直角顶出圆角外”的劣质感。
                 </p>
               </div>
               <div class="space-y-2">
                 <h4 class="text-sm font-bold text-white">一键全屏阻断</h4>
                 <p class="text-[11px] text-text-tertiary leading-relaxed">
                   所有的局部下拉菜单，必须挂载一个隐形的 <code>fixed inset-0</code> 全屏透明遮罩层（z-index略低于菜单）。从而实现真正的“点击屏幕任意区域即刻收起”。彻底抛弃传统但容易失效的 click-outside 监听器机制。
                 </p>
               </div>
             </div>
          </div>
        </div>

        <!-- Iconography -->
        <div class="space-y-10">
          <div class="flex items-center gap-4">
             <div class="p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-600/20"><Sparkles :size="24" class="text-white" /></div>
             <h2 class="text-4xl font-black uppercase tracking-tighter">06. 图标与符号 (Iconography)</h2>
          </div>
          <div class="grid md:grid-cols-3 gap-6">
            <div class="p-8 rounded-[32px] border border-white/5 bg-white/5 flex flex-col items-center gap-4 text-center">
               <div class="flex gap-4 text-indigo-400">
                 <Zap :size="24" :stroke-width="3" />
                 <Target :size="24" :stroke-width="3" />
                 <History :size="24" :stroke-width="3" />
               </div>
               <div>
                 <div class="text-xs font-black uppercase tracking-widest mt-2 text-white">Weight 3.0</div>
                 <p class="text-[11px] text-text-tertiary mt-2">全站操作图标（Header 菜单、设置、控制台）强制附加 <code>:stroke-width="3"</code>。通过加粗笔触来摆脱“纤弱网页感”，换取工业级的硬朗与光泽度。</p>
               </div>
            </div>
            <div class="p-8 rounded-[32px] border border-white/5 bg-white/5 flex flex-col items-center gap-4 text-center">
               <div class="flex gap-4 text-indigo-400 relative">
                 <Layers :size="24" :stroke-width="3" />
                 <span class="absolute -top-1.5 -right-1.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-indigo-500 px-1 text-[9px] font-black text-white ring-2 ring-[#020205]">3</span>
               </div>
               <div>
                 <div class="text-xs font-black uppercase tracking-widest mt-2 text-white">Badge Overlay</div>
                 <p class="text-[11px] text-text-tertiary mt-2">数字角标绝不附在文字后。必须绝对定位在图标右上角 (<code>-top-1.5 -right-1.5</code>)，且强制包含底色外环 <code>ring-2</code>，精准切除底图，制造深空悬浮感。</p>
               </div>
            </div>
            <div class="p-8 rounded-[32px] border border-white/5 bg-white/5 flex flex-col items-center gap-4 text-center">
               <div class="flex gap-4 text-indigo-400">
                 <MessageSquare :size="24" :stroke-width="3" class="text-indigo-500" />
                 <GitMerge :size="24" :stroke-width="3" class="text-purple-500" />
                 <Sparkles :size="24" :stroke-width="3" class="text-amber-400" />
               </div>
               <div>
                 <div class="text-xs font-black uppercase tracking-widest mt-2 text-white">Identity Semantic</div>
                 <p class="text-[11px] text-text-tertiary mt-2">抛弃含糊不清的文本段落图标。模式切换使用具象化的实物隐喻：摘要(闪电)、选中(准星)、全文(历史)。应用身份使用强识别色和对应图标强绑定。</p>
               </div>
            </div>
          </div>
        </div>

        <!-- Interactions & Cinematic Background -->
        <div class="space-y-10">
          <div class="flex items-center gap-4">
             <div class="p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-600/20"><MousePointerClick :size="24" class="text-white" /></div>
             <h2 class="text-4xl font-black uppercase tracking-tighter">07. 交互与环境 (Interactions)</h2>
          </div>
          <div class="p-8 rounded-[40px] border border-white/5 bg-white/5 backdrop-blur-xl space-y-6">
             <div class="grid md:grid-cols-2 gap-8">
               <div class="space-y-3">
                 <h4 class="text-sm font-black uppercase tracking-widest text-indigo-400">Aurora Engine (极光渲染引擎)</h4>
                 <ul class="text-sm text-text-tertiary space-y-2 list-disc pl-4">
                   <li><strong class="text-white">边缘防溢出：</strong>极光背景容器必须使用重度负外边距（如 <code>fixed -inset-[100px]</code>）铺满超视口区域。绝对禁止在鼠标剧烈滑动（Translate3d偏移）时暴露出底部的死白/死黑边界。</li>
                   <li><strong class="text-white">光学噪点融合：</strong>在极光层之上、UI 层之下，必须覆盖一层 <code>z-[9999]</code> 且 <code>pointer-events-none</code> 的全屏 SVG 噪点，配合 <code>mix-blend-overlay</code> 消除渐变色带的断层，赋予画面胶片感。</li>
                 </ul>
               </div>
               <div class="space-y-3">
                 <h4 class="text-sm font-black uppercase tracking-widest text-indigo-400">Kinetic Feedback (物理反馈)</h4>
                 <ul class="text-sm text-text-tertiary space-y-2 list-disc pl-4">
                   <li><strong class="text-white">弹性缩放：</strong>所有重要的操作组件（新对话按钮、模型卡片选中、侧边栏按钮），必须附带 <code>active:scale-95</code> (或90)。按下时向内收缩，松开时回弹，模拟真实物理按键的段落感。</li>
                   <li><strong class="text-white">Logo 呼吸：</strong>代表系统的 SparkRing Logo 圆环，在悬浮时应带有极其缓慢的 <code>logo-spin</code> 或呼吸动效，暗示系统正处于待命计算状态。</li>
                 </ul>
               </div>
             </div>
          </div>
        </div>
      </section>

      <!-- EVOLVED LAB -->
      <section v-if="activeTab === 'lab'" class="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
        <div class="lg:col-span-5 space-y-10 p-10 rounded-[40px] bg-white/5 border border-white/10 backdrop-blur-2xl">
           <h3 class="text-2xl font-black tracking-tighter uppercase flex items-center gap-2">
              <Wand2 :size="20" class="text-indigo-500" /> 基因控制
           </h3>
           <div class="space-y-8">
            <div v-for="s in glassControls" :key="s.key" class="space-y-3">
              <div class="flex justify-between text-[10px] font-black uppercase tracking-widest opacity-40">
                <span>{{ s.label }}</span>
                <span>{{ s.value }}</span>
              </div>
              <input
                type="range"
                :value="s.value"
                min="0"
                :max="s.max"
                class="w-full accent-indigo-600"
                @input="updateGlassControl(s.key, Number(($event.target as HTMLInputElement).value))"
              />
            </div>
          </div>
        </div>

        <div class="lg:col-span-7 flex flex-col items-center justify-center p-12 min-h-[600px] relative overflow-hidden group">
           <div :style="glassStyle" class="relative z-10 w-full max-w-lg aspect-video rounded-[48px] border shadow-2xl flex flex-col p-12 overflow-hidden transition-all duration-700">
              <div class="absolute inset-0 pointer-events-none opacity-[var(--v3-noise)] mix-blend-overlay"
                   style="background-image: url('https://grainy-gradients.vercel.app/noise.svg');"></div>
              <div class="flex-1 flex flex-col items-center justify-center space-y-6">
                <Eye :size="48" class="text-indigo-600 animate-pulse" />
                <div class="text-[10px] font-black uppercase tracking-[0.5em] opacity-40 italic">Live Spec Simulation</div>
              </div>
           </div>
        </div>
      </section>

    </main>

    <footer class="py-24 text-center space-y-10 border-t border-white/5 relative z-10">
       <div class="flex justify-center gap-12 text-slate-500 dark:text-white/20 text-[10px] font-black uppercase tracking-[0.4em]">
          <span>SparkRing V3 Cinematic Specification</span>
          <span>•</span>
          <span>Build 2026.03.16</span>
       </div>
       <div class="inline-flex items-center gap-4 px-10 py-4 rounded-full bg-white text-black text-xs font-black shadow-2xl">
          FINAL SPEC DELIVERED <CheckCircle2 :size="16" />
       </div>
    </footer>
  </div>
</template>

<style>
@keyframes blob {
  0%, 100% { transform: translate(0px, 0px) scale(1); }
  33% { transform: translate(50px, -80px) scale(1.1); }
  66% { transform: translate(-40px, 40px) scale(0.9); }
}
.animate-blob { animation: blob 10s infinite cubic-bezier(0.4, 0, 0.2, 1); }

.animate-gradient {
  background-size: 300% auto;
  animation: gradient 5s linear infinite;
}

@keyframes gradient {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

input[type=range] {
  -webkit-appearance: none;
  background: transparent;
}
input[type=range]::-webkit-slider-runnable-track {
  width: 100%;
  height: 4px;
  background: rgba(128, 128, 128, 0.1);
  border-radius: 2px;
}
input[type=range]::-webkit-slider-thumb {
  -webkit-appearance: none;
  height: 16px;
  width: 16px;
  border-radius: 50%;
  background: #6366f1;
  margin-top: -6px;
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.4);
  cursor: pointer;
}
</style>