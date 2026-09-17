import type { BotDefinition } from "./Bot";
import type { Model, Preset } from "./types";
import { Popover } from "./Popover";
import { QuickModelMenu } from "./QuickModelMenu";

export function BotModelPicker({ bot, presets, models, disabled, change }: {
  bot: BotDefinition; presets: Preset[]; models: Model[]; disabled?: boolean;
  change: (presetId: string) => Promise<void>;
}) {
  const value = bot.pendingPresetId || bot.presetId || "";
  const pending = presets.find(item => item.id === bot.pendingPresetId)?.name || bot.pendingPresetId;
  const label = `${bot.model ? `当前 ${bot.model}` : "选择模型"}${pending ? ` · 下一轮 ${pending}` : ""}`;
  return <Popover title="切换 Bot 模型" className="bot-chat-model-line" label={label} wide disabled={disabled}>
    {(close, open) => open && <QuickModelMenu
      presets={presets.filter(item => item.harness === "pi")}
      models={models} value={value} favorites={[]} disabled={disabled} close={close}
      change={async id => { await change(id); return true; }}
      notice="切换后下一轮生效，运行中的任务继续使用原模型。"
    >
      <p className="popover-note">Bot 的思考强度跟随 MMS 默认；Web 默认 effort 不影响 Bot。</p>
    </QuickModelMenu>}
  </Popover>;
}
