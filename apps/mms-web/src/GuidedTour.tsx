import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { starterPrompt } from "./guide-content";

export const tourSteps = ["welcome", "connection", "workspace", "model", "effort", "compose", "send", "reply", "attachments", "skills", "materials", "artifacts", "runtime", "sessions", "settings", "finish"] as const;
export type TourStep = typeof tourSteps[number];
type StepContent = { target: string[]; title: string; body: string; tip?: string };
const content: Record<TourStep, StepContent> = {
  welcome: { target: ['textarea[aria-label="任务内容"]', '#mms-help-button'], title: "第一次用 AI？从这里开始", body: "把 AI 当作可以反复沟通的助手：告诉它你想做什么，它会回答，也能帮你处理文件。接下来，我们就在这个页面一起试一次。", tip: "亮起的地方可以直接点击。随时可以跳过，再点 ? 回来。" },
  connection: { target: ['[data-guide="connect"]'], title: "先让助手连接一个模型", body: "模型是负责回答你的 AI。点击亮起的「连接服务」，按提示填入服务商给你的 API 地址和 API Key，再选择模型并保存。", tip: "API Key 是服务商给你的连接密钥。没有这些信息时，可以先熟悉页面，之后再配置。" },
  workspace: { target: ['[data-guide="workspace"]', '.home-intro select'], title: "这次在哪个文件夹里工作？", body: "点这里输入项目名，就能查找最近用过的文件夹；也可以浏览电脑上的其他目录。你让 AI 读文件、写文章或改代码时，它会从这个位置开始。", tip: "已为你选好工作文件夹，普通聊天可以直接继续。换项目时再选择其他目录；已有会话保留原路径。" },
  model: { target: ['.studio-popover:popover-open .model-picker-trigger', '.task-settings-trigger'], title: "选择帮你回答的模型", body: "点亮起的模型名称，再打开「模型与通道」选择。模型可以理解为不同的助手；通道是连接它的服务。第一次先选一个可用模型就够了。", tip: "以后也能在这里换模型，已有对话会保留。确认选择后回来，继续下一步。" },
  effort: { target: ['.studio-popover:popover-open [data-guide="effort"]', '.task-settings-trigger'], title: "effort：让它想得更深，还是更快？", body: "这里的「思考强度」就是 effort。简单问答可以选较低档，复杂分析再提高。第一次保留默认值也可以。", tip: "只显示当前模型支持的档位。高档通常更慢、用量更多，不保证回答一定更好。不能调整时，以这里的状态说明为准。" },
  compose: { target: ['textarea[aria-label="任务内容"]'], title: "像和人说话一样，写下你的想法", body: "不用学特殊命令。说清楚「我想做什么、现在有什么、希望得到什么」就行。也可以先填入下面的简单示例，看看 AI 怎样回应。", tip: "示例会追加到已有草稿后面。你可以修改，填入不会自动发送。" },
  send: { target: ['button[aria-label="发送任务"]'], title: "准备好了？点这个箭头发送", body: "确认文件夹和模型后，点击亮起的发送箭头。AI 会开始回复；你可以继续补充要求，不必一次就问得完美。", tip: "发送可能产生所选服务的用量。灰色箭头表示还没准备好，查看输入框下方的原因。" },
  reply: { target: ['.conversation-turn:last-child', '.current-activity', 'textarea[aria-label="任务内容"]'], title: "回复会出现在这里", body: "等待 AI 回答后，可以继续问「说得简单一点」「给个例子」，或补充你的要求。结果不符合预期也没关系，接着沟通就好。", tip: "你已经认识基本操作。附件、Skills 和成果等功能，可以需要时再学。" },
  attachments: { target: ['button[aria-label="添加内容"]'], title: "在需要的地方插入文件", body: "把光标放在要求旁边，拖入文件、粘贴截图，或点 + 选择文件。路径会插入正文，你可以在不同文件之间写各自的要求。浏览器没提供原路径时，Pilot 会自动保存到项目的 .pilot/attachments。", tip: "复制插入的路径可在其他会话继续用。输入 @ 可找文件，输入 / 可查看快捷命令。" },
  skills: { target: ['[data-guide="skills"]'], title: "Skills：可复用的做事方法", body: "点这里选择想做的事，例如保存进度或检查改动。内置能力无需安装，可以先用示例填入草稿。", tip: "补充自己的要求，发送后才开始。也可以不选，直接对话。" },
  materials: { target: ['.materials-access'], title: "项目资料：不用每次重新交代", body: "把项目背景、常用要求和约定保存在这里。保存并启用后，它们会加入这个文件夹后续的新消息。", tip: "只影响之后的消息。编辑、停用或删除，不会撤回已经发出的内容；有附加内容时，消息下方「附带资料」可查看来源。" },
  artifacts: { target: ['.result-panel .panel-tabs button.active', 'button[aria-label="切换成果侧栏"]'], title: "成果：看看 AI 做出了什么", body: "在这里预览生成的文章、表格、图片或静态网页。还可以查看已记录的版本和差异，下载文件，引用文字选段或图片区域让 AI 修改。", tip: "先有会话才能打开成果。选段先进入草稿，发送后才处理；查看旧版本不会回滚电脑上的文件。" },
  runtime: { target: ['.result-panel .panel-tabs button.active'], title: "过程与运行详情：了解当前状态", body: "在这里看当前模型、上下文和用量。对话中的过程可以展开，查看工具做了什么；待确认的问题需要你在卡片里回答。", tip: "停止会结束本轮执行，已经发生的文件修改不会自动撤销。模型在正文里自报身份可能不准确，请核对运行详情。" },
  sessions: { target: ['.sidebar-sessions', '.sidebar'], title: "以前的对话都在这里", body: "左侧按工作文件夹收好会话。点标题就能接着聊；上方可以新建、搜索和筛选。工作文件夹和会话旁的更多菜单可排序、重命名、归档、导出或创建分支。", tip: "移除文件夹只从侧栏隐藏，旧会话仍能继续；归档也保留内容。对话分支不会复制或回滚项目文件。" },
  settings: { target: ['.settings-tabs'], title: "设置：连接服务，调整使用习惯", body: "「模型与通道」管理连接和新会话默认值；「外观与使用」调整跟随系统的主题、强调色、字体、字号和过程折叠。Logo 旁和设置顶部都能看到当前版本。", tip: "设置中的长期默认 effort 用于之后的新会话；已有会话仍可单独调整。" },
  finish: { target: ['#mms-help-button'], title: "忘了怎么用，随时点 ?", body: "你不用一次记住所有功能。这里可以重新开始悬浮引导，也能搜索功能说明，只了解眼下需要的部分。", tip: "现在可以回到对话，把你的第一个想法交给 AI。" },
};
interface Box { x: number; y: number; width: number; height: number }
interface Layout { box: Box | null; left: number; top: number; side: string; arrow: number; paused: boolean }
function visibleTarget(selectors: string[]) {
  for (const selector of selectors) {
    const found = [...document.querySelectorAll<HTMLElement>(selector)].find(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
    if (found) return found;
  }
  return null;
}

/** A non-modal top-layer coachmark. It never intercepts clicks on the real controls. */
export function GuidedTour({ step, move, close, help, example, modelReady, configure, hasSession }: {
  step: TourStep; move: (step: TourStep) => void; close: () => void; help: () => void;
  example: (text: string) => void; modelReady: boolean; configure: boolean; hasSession: boolean;
}) {
  const layer = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLElement>(null);
  const [layout, setLayout] = useState<Layout>({ box: null, left: 12, top: 80, side: "none", arrow: 24, paused: false });
  const steps = modelReady ? tourSteps.filter(s => s !== "connection") : [...tourSteps];
  const index = steps.indexOf(step);
  const firstCount = steps.indexOf("reply") + 1;
  const item = content[step];
  const more = index >= firstCount;
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let previous = "";
    let scrolled: HTMLElement | null = null;
    let focusCard = true;
    let lastMenu: Element | null = null;
    if (step === "effort" && !document.querySelector('.studio-popover:popover-open [data-guide="effort"]')) document.querySelector<HTMLButtonElement>('.task-settings-trigger')?.click();
    const update = () => {
      // Real dialogs (connection, file picker, model choice) own focus while open.
      const paused = !!document.querySelector('dialog[open]:not([data-guide-dialog="settings"])');
      const menu = document.querySelector('.studio-popover:popover-open');
      if (paused) layer.current?.hidePopover();
      else if (layer.current) {
        if (menu !== lastMenu && layer.current.matches(':popover-open')) layer.current.hidePopover();
        if (!layer.current.matches(':popover-open')) layer.current.showPopover();
      }
      lastMenu = menu;
      const target = visibleTarget(item.target);
      if (target && scrolled !== target && !paused) {
        target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
        scrolled = target;
      }
      const r = target?.getBoundingClientRect();
      const vw = window.innerWidth, vh = window.innerHeight;
      const box = r ? { x: Math.max(4, r.left - 5), y: Math.max(4, r.top - 5), width: Math.min(r.width + 10, vw - 8), height: Math.min(r.height + 10, vh - 8) } : null;
      // Keep the explanation outside the whole open menu so its other controls remain usable.
      const avoid = menu?.getBoundingClientRect() || r;
      const cw = Math.min(352, vw - 24), ch = card.current?.offsetHeight || 280;
      let left = (vw - cw) / 2, top = Math.max(12, (vh - ch) / 2), side = "none", arrow = cw / 2;
      if (box && avoid) {
        left = Math.max(12, Math.min(box.x + box.width / 2 - cw / 2, vw - cw - 12));
        if (avoid.bottom + ch + 22 <= vh) { top = avoid.bottom + 16; side = "top"; }
        else if (avoid.top >= ch + 22) { top = avoid.top - ch - 16; side = "bottom"; }
        else if (avoid.right + cw + 24 <= vw) { left = avoid.right + 16; top = Math.max(12, Math.min(box.y, vh - ch - 12)); side = "left"; }
        else { top = Math.max(12, vh - ch - 12); }
        arrow = Math.max(20, Math.min(cw - 20, box.x + box.width / 2 - left));
      }
      const next = { box, left, top, side, arrow, paused };
      const signature = JSON.stringify(next);
      if (signature !== previous) { previous = signature; setLayout(next); }
      if (!paused && focusCard) { card.current?.focus({ preventScroll: true }); focusCard = false; }
      timer = setTimeout(update, 120);
    };
    timer = setTimeout(update, 120);
    return () => { clearTimeout(timer); layer.current?.hidePopover(); };
  }, [step, item]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || document.querySelector('dialog[open]') || document.querySelector('.studio-popover:popover-open')) return;
      event.preventDefault(); close(); document.getElementById('mms-help-button')?.focus();
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [close]);
  const last = step === "finish";
  const next = () => move(steps[index + 1]);
  const body = step === "connection" && modelReady ? "已经发现可用模型，可以直接继续。如果要连接自己的其他服务，点击亮起的入口，按提示配置。" : step === "connection" && !configure ? "当前模型来自已有 MMF 配置。点击亮起的入口查看来源；有可用模型时可以直接继续。" : item.body;
  return <div ref={layer} popover="manual" className="tour-layer" aria-label="悬浮使用引导">
    {layout.box && <div className="tour-spotlight" aria-hidden="true" style={{ left: layout.box.x, top: layout.box.y, width: layout.box.width, height: layout.box.height }} />}
    <section ref={card} className="tour-card" tabIndex={-1} role="dialog" aria-modal="false" aria-labelledby="tour-title" aria-describedby="tour-body" style={{ left: layout.left, top: layout.top, width: 'min(352px, calc(100vw - 24px))' }}>
      {layout.box && layout.side !== "none" && <i className={`tour-arrow ${layout.side}`} style={layout.side === "left" ? { top: 28 } : { left: layout.arrow }} aria-hidden="true" />}
      <header><span>{more ? `认识更多功能 · ${index - firstCount + 1} / 8` : `开始第一条对话 · ${Math.min(index + 1, firstCount)} / ${firstCount}`}</span><button type="button" className="icon-button" aria-label="跳过悬浮引导" onClick={close}><X size={16} /></button></header>
      <h2 id="tour-title">{item.title}</h2><p id="tour-body">{body}</p>
      {item.tip && <p className="tour-tip">{item.tip}</p>}
      {!layout.box && <p className="tour-tip" role="status">{!hasSession && (step === "artifacts" || step === "runtime") ? "开始或打开一条会话后，这个入口就会出现。可以先跳到下一项。" : "当前页面暂未显示这个入口，可以先了解说明或跳到下一步。"}</p>}
      {step === "compose" && <button className="button tour-example" type="button" onClick={() => example(starterPrompt)}>帮我填入一条示例</button>}
      {step === "send" && !modelReady && <button className="text-button" type="button" onClick={() => move("connection")}>还没有可用模型，去连接服务</button>}
      <footer><button type="button" className="text-button" disabled={index === 0} onClick={() => move(steps[index - 1])}><ArrowLeft size={14} />上一步</button><button type="button" className="button primary" onClick={last || step === "send" ? close : next}>{last ? "知道了" : step === "send" ? "稍后再发" : step === "reply" ? "认识更多功能" : "下一步"}{!last && step !== "send" && <ArrowRight size={14} />}</button></footer>
      <div className="tour-links"><button type="button" onClick={close}>先自己试试</button><button type="button" onClick={help}>查功能说明</button></div>
    </section>
  </div>;
}
