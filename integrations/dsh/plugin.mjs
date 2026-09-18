/** MMS Recipe commands and actual-request capability gate, using public DSH seams. */
import { mkdirSync, readFileSync, readdirSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';
import { createUserMessage } from '@deepseek-ai/dsh-llm';
export const name = 'mms-recipe';
export const inject = ['commands', 'llm', 'skills'];

export function checkRequirements(recipe, info, skills) {
  if (recipe.modelRequirements.image && !info.inputModalities?.includes('image'))
    throw new Error('实际所选通道不满足模板的图片输入要求，请重新选择模型。');
  if (recipe.modelRequirements.reasoning && !info.reasoning?.efforts?.some(e => e.id !== 'off'))
    throw new Error('实际所选通道未声明模板要求的推理能力，请重新选择模型。');
  for (const name of recipe.requiredSkills) {
    if (skills.filter(s => s.name === name && s.invocation.modelInvocable).length !== 1)
      throw new Error(`实际会话没有可用的唯一 Skill ${name}，请配置后重试。`);
  }
}

export async function apply(ctx, config) {
  const { parseRecipe, renderRecipe } = await import(config.recipeCore);
  const recipes = join(config.root, 'recipes');
  const states = join(config.root, 'recipe-state');
  mkdirSync(recipes, {recursive: true, mode: 0o700});
  mkdirSync(states, {recursive: true, mode: 0o700});
  const statePath = agent => join(states, createHash('sha256').update(String(agent.session.id)).digest('hex') + '.json');
  function writeState(agent, state) {
    const path = statePath(agent);
    writeFileSync(path + '.tmp', JSON.stringify(state), {mode: 0o600});
    renameSync(path + '.tmp', path);
  }
  function stateFor(agent) {
    try { return JSON.parse(readFileSync(statePath(agent), 'utf8')); }
    catch (e) { if (e.code === 'ENOENT') return null; throw new Error('Recipe 状态无法读取，已停止请求。'); }
  }
  function loadRecipe(path) {
    if (statSync(path).size > 128000) throw new Error('Recipe 必须小于 128 KB。');
    return parseRecipe(readFileSync(path, 'utf8'));
  }
  // Runs after the selected model's waterfall; validates the frozen actual request.
  ctx.on('agent/request', async ({agent}, next) => {
    const call = await next();
    const state = stateFor(agent);
    if (!state) return call;
    const info = await ctx.llm.resolveModelInfo(call.provider, call.model);
    const skills = await ctx.skills.list({scope: agent, cwd: agent.session.header.cwd});
    checkRequirements(state.recipe, info, skills);
    return call;
  });
  ctx.commands.register({
    name: 'recipe', description: 'MMS 任务模板：导入、填变量、检查实际模型能力',
    input: {hint: 'list | import <绝对路径> | use <id> {"变量":"值"} | clear'},
    async handler({agent, rawInput}) {
      try {
        const input = rawInput.trim();
        if (input === 'list' || !input) {
          const items = readdirSync(recipes).filter(f => f.endsWith('.json')).map(f => {
            const r = loadRecipe(join(recipes, f)); return `${f.slice(0, -5)} · ${r.title}`;
          });
          return {kind: 'success', text: ['MMS Recipe', ...items, '用法：/recipe use <id> {"变量":"值"}', '导入：/recipe import <绝对路径>'].join('\n')};
        }
        if (input.startsWith('import ')) {
          const path = input.slice(7).trim();
          if (!path.startsWith('/')) throw new Error('请输入本机模板文件的绝对路径。');
          const r = loadRecipe(resolve(path));
          const id = createHash('sha256').update(JSON.stringify(r)).digest('hex').slice(0, 12);
          writeFileSync(join(recipes, id + '.json'), JSON.stringify(r, null, 2), {mode: 0o600});
          return {kind: 'success', text: `已导入：${r.title}\n使用：/recipe use ${id}`};
        }
        if (agent.status !== 'idle') throw new Error('请等当前回复结束，再更换模板。');
        if (input === 'clear') {
          writeState(agent, null);
          return {kind: 'success', text: '已清除本会话的 Recipe 要求。'};
        }
        const match = /^use ([a-zA-Z0-9_-]+)(?:\s+(\{.*\}))?$/s.exec(input);
        if (!match) throw new Error('用法：/recipe use <id> {"变量":"值"}');
        const recipe = loadRecipe(join(recipes, match[1] + '.json'));
        if (recipe.planning) throw new Error('此适配器尚未接入规划模式，请在 Pilot 运行此模板。');
        const values = match[2] ? JSON.parse(match[2]) : {};
        const prompt = renderRecipe(recipe, values);
        // Capability checks belong to the request waterfall, so a concurrent model
        // switch cannot bypass them. Pending state is durable before queuing.
        writeState(agent, {recipe});
        agent.followup(createUserMessage({content: [{type: 'text', text: prompt}], source: {kind: 'user'}}));
        return {kind: 'success', text: `已使用「${recipe.title}」。发送前核对实际模型与 Skills；偏好模型不会覆盖你的选择。`};
      } catch (e) { return {kind: 'error', text: e.code === 'ENOENT' ? '未找到模板文件。' : e.message}; }
    },
  });
}
