<template>
  <div class="flex h-full flex-col bg-surface-1">
    <div class="flex-1 overflow-y-auto">
      <div v-if="!store.isActive && !store.isStreaming" class="mx-auto max-w-6xl px-4 py-6 md:px-6 md:py-8">
        <section class="overflow-hidden rounded-[1.75rem] border border-gray-200 bg-white shadow-card">
          <div class="grid gap-6 px-6 py-6 md:grid-cols-[1.1fr_0.9fr] md:px-8">
            <div>
              <div class="mb-4 inline-flex items-center gap-2 rounded-full border border-purple-200 bg-purple-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-purple-700">
                AI Role Committee
              </div>
              <h1 class="max-w-3xl text-3xl font-semibold leading-tight text-gray-900 md:text-[2.35rem]">
                不是让 AI 给你一个答案，而是让一群立场不同的角色当面思考。
              </h1>
              <p class="mt-4 max-w-2xl text-sm leading-7 text-gray-500 md:text-base">
                多模型深度讨论在这里升级为“角色委员会”。每个角色都有固定世界观、立场轴和不可妥协点，
                你看到的不是多人重复，而是有张力的公开推演。
              </p>

              <div class="mt-6 grid gap-3 sm:grid-cols-3">
                <button
                  v-for="mode in modeOptions"
                  :key="mode.id"
                  @click="selectedMode = mode.id"
                  class="rounded-[1.4rem] border px-4 py-4 text-left transition-all duration-200"
                  :class="selectedMode === mode.id
                    ? 'border-purple-300 bg-purple-50 shadow-card'
                    : 'border-gray-200 bg-gray-50 hover:border-gray-300 hover:bg-white'"
                >
                  <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-purple-600">{{ mode.tagline }}</div>
                  <div class="mt-2 text-lg font-semibold text-gray-900">{{ mode.name }}</div>
                  <p class="mt-2 text-xs leading-6 text-gray-500">{{ mode.description }}</p>
                </button>
              </div>
            </div>

            <div class="rounded-[1.5rem] border border-gray-200 bg-gray-50 p-5">
              <div class="flex items-center justify-between">
                <div>
                  <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-gray-400">Model Pool</div>
                  <div class="mt-2 text-lg font-semibold text-gray-900">绑定模型池</div>
                </div>
                <button
                  @click="showModelSheet = true"
                  class="inline-flex items-center gap-1 rounded-full border border-purple-200 bg-white px-3 py-1.5 text-xs font-medium text-purple-700 transition-colors hover:bg-purple-50"
                >
                  <Plus class="h-3.5 w-3.5" />
                  绑定模型
                </button>
              </div>

              <div class="mt-4 flex flex-wrap gap-2">
                <ModelChip
                  v-for="model in appStore.discussSelectedModelObjects"
                  :key="model.id"
                  :model="model"
                  removable
                  @remove="appStore.toggleModel('discuss', model.id)"
                />
              </div>

              <div class="mt-5 rounded-[1.4rem] border border-gray-200 bg-white p-4">
                <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-gray-400">当前运行</div>
                <div class="mt-3 grid gap-3 sm:grid-cols-2">
                  <div class="rounded-2xl border border-gray-200 bg-gray-50 p-3">
                    <div class="text-xs text-gray-400">激活角色</div>
                    <div class="mt-1 text-2xl font-semibold text-gray-900">{{ selectedRoleIds.length }}</div>
                  </div>
                  <div class="rounded-2xl border border-gray-200 bg-gray-50 p-3">
                    <div class="text-xs text-gray-400">模式</div>
                    <div class="mt-1 text-lg font-semibold text-gray-900">{{ currentModeOption?.name }}</div>
                  </div>
                </div>
                <p class="mt-4 text-xs leading-6 text-gray-500">
                  系统会按角色职责自动分配模型，关键角色优先拿更强的模型，中枢和补充角色再按能力匹配与复用。
                </p>
              </div>
            </div>
          </div>
        </section>

        <section class="mt-6 rounded-[2rem] border border-slate-200/80 bg-white/90 p-5 shadow-[0_20px_70px_rgba(148,163,184,0.12)] md:p-6">
          <div>
            <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Committee Packs</div>
            <div class="mt-2 flex items-end justify-between gap-4">
              <div>
                <h2 class="text-2xl font-semibold text-slate-950">任务委员会包</h2>
                <p class="mt-2 max-w-3xl text-sm leading-7 text-slate-500">
                  先覆盖产品、运营、设计三类高频场景。它们共用同一套 12 角框架，只是在不同工作对象下，激活不同角色组合。
                </p>
              </div>
            </div>
          </div>

          <div class="mt-5 grid gap-3 lg:grid-cols-3">
            <button
              v-for="pack in committeePacks"
              :key="pack.id"
              @click="selectCommitteePack(pack.id)"
              class="rounded-[1.4rem] border p-4 text-left transition-all duration-200"
              :class="activePackId === pack.id
                ? 'border-slate-900 bg-slate-900 text-white shadow-card'
                : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div
                    class="text-[11px] font-semibold uppercase tracking-[0.22em]"
                    :class="activePackId === pack.id ? 'text-slate-300' : 'text-slate-400'"
                  >
                    {{ pack.subtitle }}
                  </div>
                  <div class="mt-2 text-lg font-semibold">{{ pack.name }}</div>
                </div>
                <div
                  class="rounded-full px-2 py-1 text-[10px] font-medium"
                  :class="activePackId === pack.id ? 'bg-white/10 text-white' : 'bg-white text-slate-500 ring-1 ring-slate-200'"
                >
                  {{ pack.outcomes.length }} 类
                </div>
              </div>
              <p
                class="mt-3 text-xs leading-6"
                :class="activePackId === pack.id ? 'text-slate-200' : 'text-slate-500'"
              >
                {{ pack.description }}
              </p>
              <div class="mt-3 flex flex-wrap gap-1.5">
                <span
                  v-for="outcome in pack.outcomes"
                  :key="outcome"
                  class="rounded-full px-2 py-0.5 text-[10px]"
                  :class="activePackId === pack.id ? 'bg-white/10 text-slate-100' : 'bg-white text-slate-500 ring-1 ring-slate-200'"
                >
                  {{ outcome }}
                </span>
              </div>
            </button>
          </div>

          <div class="my-6 h-px bg-slate-200" />

          <div>
            <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Recommended</div>
            <div class="mt-2 flex items-center justify-between gap-4">
              <div>
                <h2 class="text-2xl font-semibold text-slate-950">猜你喜欢</h2>
                <p class="mt-2 max-w-3xl text-sm leading-7 text-slate-500">
                  当前正在查看
                  <span class="font-semibold text-slate-700">{{ activePack?.name }}</span>
                  下的常用组合。点击后会切换角色子集，并带上推荐的运行模式。
                </p>
              </div>
            </div>
          </div>

          <div class="mt-5 grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
            <button
              v-for="preset in filteredCommitteePresets"
              :key="preset.id"
              @click="applyCommitteePreset(preset.id)"
              class="rounded-[1.4rem] border p-4 text-left transition-all duration-200"
              :class="activePresetId === preset.id
                ? 'border-slate-900 bg-slate-900 text-white shadow-card'
                : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div
                    class="text-[11px] font-semibold uppercase tracking-[0.22em]"
                    :class="activePresetId === preset.id ? 'text-slate-300' : 'text-slate-400'"
                  >
                    {{ modeLabelMap[preset.mode] }}
                  </div>
                  <div class="mt-2 text-base font-semibold">{{ preset.name }}</div>
                </div>
                <div
                  class="rounded-full px-2 py-1 text-[10px] font-medium"
                  :class="activePresetId === preset.id ? 'bg-white/10 text-white' : 'bg-white text-slate-500 ring-1 ring-slate-200'"
                >
                  {{ preset.roleIds.length }} 角
                </div>
              </div>
              <div
                class="mt-2 text-xs"
                :class="activePresetId === preset.id ? 'text-slate-300' : 'text-slate-500'"
              >
                {{ preset.subtitle }}
              </div>
              <p
                class="mt-3 text-xs leading-6"
                :class="activePresetId === preset.id ? 'text-slate-200' : 'text-slate-500'"
              >
                {{ preset.description }}
              </p>
            </button>
          </div>

          <div class="my-6 h-px bg-slate-200" />

          <div class="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Persona Matrix</div>
              <h2 class="mt-2 font-serif text-2xl text-slate-950">12 个预设角色，按职能克制</h2>
              <p class="mt-2 max-w-3xl text-sm leading-7 text-slate-500">
                普通用户只需要直接勾选角色，高级定制放到后续版本。当前重点是验证：不同角色是否能对同一问题给出真的有张力的分析。
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button
                @click="showAssignments = !showAssignments"
                class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
              >
                {{ showAssignments ? '隐藏分配' : '查看分配' }}
              </button>
              <button
                @click="selectAllRoles"
                class="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
              >
                全选 12 角
              </button>
              <button
                @click="clearRoles"
                class="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
              >
                清空
              </button>
            </div>
          </div>

          <div class="mt-6 grid gap-4 xl:grid-cols-2">
            <div
              v-for="group in roleGroups"
              :key="group.category"
              class="rounded-[1.6rem] border border-slate-200/70 bg-slate-50/80 p-4"
            >
              <div class="mb-3 flex items-center justify-between">
                <div>
                  <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">{{ group.tag }}</div>
                  <div class="mt-1 text-lg font-semibold text-slate-900">{{ group.label }}</div>
                </div>
                <button
                  @click="toggleCategory(group.category)"
                  class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-medium text-slate-600 transition-colors hover:border-slate-300"
                >
                  {{ isCategoryFullySelected(group.category) ? '取消整组' : '整组激活' }}
                </button>
              </div>

              <div class="grid gap-3 md:grid-cols-2">
                <button
                  v-for="role in group.roles"
                  :key="role.id"
                  @click="toggleRole(role.id)"
                  class="relative overflow-hidden rounded-[1.4rem] border bg-white p-4 text-left transition-all duration-200"
                  :class="selectedRoleIds.includes(role.id)
                    ? 'border-slate-900 shadow-[0_16px_32px_rgba(15,23,42,0.10)]'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'"
                >
                  <div class="absolute inset-x-0 top-0 h-1 bg-gradient-to-r" :class="role.color" />
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <div class="text-sm font-semibold text-slate-900">{{ role.name }}</div>
                      <div class="mt-1 text-xs text-slate-500">{{ role.title }}</div>
                    </div>
                    <div
                      class="rounded-full px-2 py-1 text-[10px] font-semibold"
                      :class="selectedRoleIds.includes(role.id)
                        ? 'bg-slate-900 text-white'
                        : 'bg-slate-100 text-slate-500'"
                    >
                      {{ selectedRoleIds.includes(role.id) ? 'Active' : 'Idle' }}
                    </div>
                  </div>

                  <div class="mt-3 flex flex-wrap gap-1.5 text-[10px]">
                    <span class="rounded-full bg-cyan-50 px-2 py-0.5 text-cyan-700">{{ role.axes.outlook }}</span>
                    <span class="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700">{{ role.axes.horizon }}</span>
                    <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">{{ role.axes.interest }}</span>
                  </div>

                  <p class="mt-3 text-xs leading-6 text-slate-600">{{ role.coreBelief }}</p>
                  <p class="mt-2 text-[11px] leading-6 text-slate-400">不可妥协：{{ role.nonNegotiable }}</p>

                  <div
                    v-if="showAssignments && assignmentMap[role.id]"
                    class="mt-3 rounded-xl border border-purple-100 bg-purple-50/70 px-3 py-2"
                  >
                    <div class="flex items-center justify-between gap-2">
                      <span class="text-[11px] font-medium text-purple-700">当前模型</span>
                      <span class="truncate text-[11px] font-semibold text-slate-700">
                        {{ appStore.getModelName(assignmentMap[role.id].modelId) }}
                      </span>
                    </div>
                    <div class="mt-2 flex flex-wrap gap-1.5">
                      <span
                        v-for="reason in assignmentMap[role.id].reasons.slice(0, 2)"
                        :key="reason"
                        class="rounded-full bg-white px-2 py-0.5 text-[10px] text-slate-500 ring-1 ring-purple-100"
                      >
                        {{ reason }}
                      </span>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div v-else class="mx-auto max-w-6xl px-4 py-6 md:px-6">
        <div class="relative">
          <div class="absolute left-5 top-0 bottom-0 hidden w-px bg-slate-200 md:block" />

          <div class="relative mb-8 flex items-start gap-4">
            <div class="z-10 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-slate-950 shadow-sm">
              <MessageSquare class="h-4 w-4 text-white" />
            </div>
            <div class="flex-1 rounded-[1.5rem] border border-slate-200 bg-white/90 px-4 py-4 shadow-card">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full bg-slate-950 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-white">
                  {{ startedModeOption?.name }}
                </span>
                <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-medium text-slate-500">
                  {{ store.activeRoleCount }} 个角色
                </span>
                <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-medium text-slate-500">
                  {{ appStore.discussSelectedModelObjects.length }} 个模型池
                </span>
              </div>
              <p class="mt-3 text-base font-medium leading-7 text-slate-900">{{ store.prompt }}</p>
            </div>
          </div>

          <PhaseSection
            :phase="1"
            title="角色独立发言"
            :subtitle="`${store.activeRoleCount} 个 Persona 并行输出`"
            :current="store.currentPhase"
            :status="store.currentPhase > 1 || (store.phaseStatus === 'completed' && !store.hasDebatePhase && !store.hasCommitteePhase)
              ? 'done'
              : 'running'"
            color-class="bg-slate-950"
          >
            <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <SummaryCard
                v-for="summary in store.phase1Summaries"
                :key="summary.roleId"
                :summary="summary"
                :role="roleMap[summary.roleId]"
                :model-name="appStore.getModelName(summary.modelId)"
              />
            </div>
          </PhaseSection>

          <PhaseSection
            v-if="store.hasDebatePhase"
            :phase="2"
            title="第二轮正面回应"
            subtitle="立场不改变，但必须回应对方"
            :current="store.currentPhase"
            :status="store.phaseStatus === 'completed' ? 'done' : store.currentPhase === 2 ? 'running' : 'waiting'"
            color-class="bg-rose-600"
          >
            <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ReviewCard
                v-for="review in store.phase2Reviews"
                :key="`${review.roleId}-${review.targetRoleId}`"
                :review="review"
                :role-name="roleMap[review.roleId]?.name || review.roleId"
                :target-name="roleMap[review.targetRoleId]?.name || review.targetRoleId"
              />
            </div>
          </PhaseSection>

          <PhaseSection
            v-if="store.hasCommitteePhase"
            :phase="3"
            title="系统级委员会汇总"
            :subtitle="store.synthesizer || ''"
            :current="store.currentPhase"
            :status="store.phaseStatus === 'completed' ? 'done' : 'running'"
            color-class="bg-amber-500"
          >
            <div class="space-y-4">
              <div class="overflow-hidden rounded-[1.4rem] border border-gray-200 bg-white shadow-card">
                <div class="border-b border-gray-100 bg-gray-50 px-5 py-4">
                  <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Committee Output</div>
                  <div class="mt-2 flex flex-wrap gap-2">
                    <span
                      v-for="item in store.committeeContributions"
                      :key="item.roleId"
                      class="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-gray-200"
                    >
                      {{ roleMap[item.roleId]?.name }} · {{ item.label }}
                    </span>
                  </div>
                </div>
                <div class="px-5 py-4 text-sm">
                  <div class="prose-chat max-w-none" v-html="renderedSynthesis" />
                  <div v-if="store.isStreaming && store.currentPhase === 3" class="pt-3">
                    <span class="inline-flex gap-1">
                      <span class="h-1.5 w-1.5 rounded-full bg-amber-400 animate-typing" style="animation-delay:0s" />
                      <span class="h-1.5 w-1.5 rounded-full bg-amber-400 animate-typing" style="animation-delay:0.2s" />
                      <span class="h-1.5 w-1.5 rounded-full bg-amber-400 animate-typing" style="animation-delay:0.4s" />
                    </span>
                  </div>
                </div>
              </div>

              <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <section class="rounded-[1.4rem] border border-gray-200 bg-white shadow-card">
                  <div class="border-b border-gray-100 px-5 py-4">
                    <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-600">Consensus</div>
                    <h4 class="mt-1 text-base font-semibold text-gray-900">共识</h4>
                  </div>
                  <div class="space-y-3 px-5 py-4">
                    <div v-for="item in store.committeeSynthesis?.consensus || []" :key="item.id" class="rounded-2xl bg-gray-50 p-4">
                      <div class="text-sm font-semibold text-gray-900">{{ item.title }}</div>
                      <p class="mt-2 text-xs leading-6 text-gray-600">{{ item.summary }}</p>
                      <div class="mt-3 flex flex-wrap gap-2">
                        <span
                          v-for="roleId in item.roleIds"
                          :key="roleId"
                          class="rounded-full bg-white px-2 py-1 text-[11px] font-medium text-gray-500 ring-1 ring-gray-200"
                        >
                          {{ roleMap[roleId]?.name }}
                        </span>
                      </div>
                    </div>
                  </div>
                </section>

                <section class="rounded-[1.4rem] border border-gray-200 bg-white shadow-card">
                  <div class="border-b border-gray-100 px-5 py-4">
                    <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-rose-600">Tensions</div>
                    <h4 class="mt-1 text-base font-semibold text-gray-900">主要分歧</h4>
                  </div>
                  <div class="space-y-3 px-5 py-4">
                    <div v-for="item in store.committeeSynthesis?.tensions || []" :key="item.id" class="rounded-2xl bg-gray-50 p-4">
                      <div class="text-sm font-semibold text-gray-900">{{ item.title }}</div>
                      <p class="mt-2 text-xs leading-6 text-gray-600">{{ item.summary }}</p>
                      <div class="mt-3 flex flex-wrap gap-2">
                        <span
                          v-for="roleId in item.roleIds"
                          :key="roleId"
                          class="rounded-full bg-white px-2 py-1 text-[11px] font-medium text-gray-500 ring-1 ring-gray-200"
                        >
                          {{ roleMap[roleId]?.name }}
                        </span>
                      </div>
                    </div>
                  </div>
                </section>

                <section class="rounded-[1.4rem] border border-gray-200 bg-white shadow-card xl:col-span-2">
                  <div class="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
                    <div>
                      <div class="border-b border-gray-100 px-5 py-4">
                        <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-blue-600">Actions</div>
                        <h4 class="mt-1 text-base font-semibold text-gray-900">建议动作</h4>
                      </div>
                      <div class="space-y-3 px-5 py-4">
                        <div v-for="item in store.committeeSynthesis?.actions || []" :key="item.id" class="rounded-2xl bg-gray-50 p-4">
                          <div class="text-sm font-semibold text-gray-900">{{ item.title }}</div>
                          <p class="mt-2 text-xs leading-6 text-gray-600">{{ item.summary }}</p>
                          <div class="mt-3 flex flex-wrap gap-2">
                            <span
                              v-for="roleId in item.roleIds"
                              :key="roleId"
                              class="rounded-full bg-white px-2 py-1 text-[11px] font-medium text-gray-500 ring-1 ring-gray-200"
                            >
                              {{ roleMap[roleId]?.name }}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div class="border-t border-gray-100 xl:border-l xl:border-t-0">
                      <div class="px-5 py-4">
                        <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-amber-600">Minority</div>
                        <h4 class="mt-1 text-base font-semibold text-gray-900">少数派意见</h4>
                      </div>
                      <div class="space-y-3 px-5 pb-5">
                        <div v-for="item in store.committeeSynthesis?.minority || []" :key="item.id" class="rounded-2xl bg-amber-50 p-4">
                          <div class="text-sm font-semibold text-gray-900">{{ item.title }}</div>
                          <p class="mt-2 text-xs leading-6 text-gray-600">{{ item.summary }}</p>
                          <div class="mt-3 flex flex-wrap gap-2">
                            <span
                              v-for="roleId in item.roleIds"
                              :key="roleId"
                              class="rounded-full bg-white px-2 py-1 text-[11px] font-medium text-gray-500 ring-1 ring-amber-200"
                            >
                              {{ roleMap[roleId]?.name }}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </section>
              </div>
            </div>
          </PhaseSection>
        </div>

        <div class="h-10" />
      </div>
    </div>

    <div class="border-t border-slate-200/80 bg-white/85 backdrop-blur-sm safe-bottom">
      <div v-if="!store.isActive && !store.isStreaming" class="px-4 py-3">
        <div class="mx-auto max-w-4xl">
          <div class="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span class="rounded-full bg-slate-100 px-2.5 py-1">{{ currentModeOption?.name }}</span>
            <span class="rounded-full bg-slate-100 px-2.5 py-1">{{ selectedRoleIds.length }} 个角色已激活</span>
          </div>
          <div class="flex items-end gap-2">
            <div class="flex-1 rounded-[1.3rem] border border-slate-200 bg-slate-50 transition-all focus-within:border-slate-900 focus-within:bg-white focus-within:ring-2 focus-within:ring-slate-200">
              <textarea
                v-model="inputText"
                rows="2"
                placeholder="输入要交给委员会的问题，例如：这个产品应该先做 12 个预设角色，还是先做角色自定义？"
                class="max-h-[120px] w-full resize-none bg-transparent px-4 py-3 text-sm leading-7 text-slate-800 focus:outline-none"
                @keydown="handleKeydown"
              />
            </div>
            <button
              @click="handleSubmit"
              :disabled="!canSubmit"
              class="inline-flex items-center gap-2 rounded-[1.2rem] bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Sparkles class="h-4 w-4" />
              启动委员会
            </button>
          </div>
        </div>
      </div>

      <div v-else-if="store.isActive && !store.isStreaming" class="px-4 py-3">
        <div class="mx-auto flex max-w-6xl items-center justify-between gap-3">
          <div class="flex items-center gap-2 text-sm text-slate-500">
            <CheckCircle class="h-4 w-4 text-emerald-500" />
            委员会运行完成
          </div>
          <div class="flex items-center gap-2">
            <button
              @click="continueToChat"
              class="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-cyan-700 transition-colors hover:bg-cyan-50"
            >
              <MessageSquare class="h-3.5 w-3.5" />
              继续对话
            </button>
            <button
              @click="store.clearSession()"
              class="rounded-full px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-100"
            >
              结束
            </button>
            <button
              @click="startNew"
              class="rounded-full bg-slate-950 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-slate-800"
            >
              新问题
            </button>
          </div>
        </div>
      </div>

      <div v-else class="px-4 py-3">
        <div class="mx-auto flex max-w-6xl items-center gap-3 text-sm text-slate-500">
          <Loader2 class="h-4 w-4 animate-spin text-cyan-600" />
          <span>{{ phaseNames[store.currentPhase] }}中...</span>
          <span class="text-xs text-slate-400">{{ store.phaseProgress.current }}/{{ store.phaseProgress.total }}</span>
        </div>
      </div>
    </div>

    <ModelSheet v-model:open="showModelSheet" mode="discuss" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import MarkdownIt from 'markdown-it'
import {
  CheckCircle,
  Loader2,
  MessageSquare,
  Plus,
  Sparkles,
} from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'
import { useDiscussStore } from '@/stores/discuss'
import {
  buildRoleModelAssignments,
  COMMITTEE_MODE_OPTIONS,
  COMMITTEE_PACKS,
  COMMITTEE_PRESETS,
  COMMITTEE_ROLES,
  type CommitteeMode,
  type CommitteePack,
  type CommitteePhase,
  type RoleCategoryId,
} from '@/features/committee'
import ModelChip from '@/components/ModelChip.vue'
import ModelSheet from '@/components/ModelSheet.vue'
import PhaseSection from '@/components/PhaseSection.vue'
import ReviewCard from '@/components/ReviewCard.vue'
import SummaryCard from '@/components/SummaryCard.vue'

const appStore = useAppStore()
const store = useDiscussStore()
const router = useRouter()
const md = new MarkdownIt()

const inputText = ref('')
const showModelSheet = ref(false)
const showAssignments = ref(false)
const selectedMode = ref<CommitteeMode>('broadcast')
const selectedRoleIds = ref(COMMITTEE_ROLES.map((role) => role.id))
const selectedPackId = ref('product')

const roleMap = Object.fromEntries(COMMITTEE_ROLES.map((role) => [role.id, role]))
const modeOptions = COMMITTEE_MODE_OPTIONS
const committeePacks = COMMITTEE_PACKS
const committeePresets = COMMITTEE_PRESETS

const modeLabelMap: Record<CommitteeMode, string> = {
  broadcast: '广播模式',
  debate: '辩论模式',
  committee: '委员会模式',
}

const roleGroupSeeds: Array<{ category: RoleCategoryId; label: string; tag: string }> = [
  { category: 'strategy', label: '战略与方向', tag: 'Long-Term Direction' },
  { category: 'risk', label: '风险与安全', tag: 'Failure & Safety' },
  { category: 'feasibility', label: '可行性与资源', tag: 'Feasibility & Resourcing' },
  { category: 'market', label: '商业与市场', tag: 'Market & Business' },
  { category: 'experience', label: '用户与体验', tag: 'User & Experience' },
  { category: 'execution', label: '执行与落地', tag: 'Execution & Delivery' },
]

const roleGroups = roleGroupSeeds.map((group) => ({
  ...group,
  roles: COMMITTEE_ROLES.filter((role) => role.category === group.category),
}))

const currentModeOption = computed(() =>
  modeOptions.find((mode) => mode.id === selectedMode.value)
)
const startedModeOption = computed(() =>
  modeOptions.find((mode) => mode.id === store.sessionMode)
)
const activePack = computed<CommitteePack | undefined>(() =>
  committeePacks.find((pack) => pack.id === selectedPackId.value)
)
const activePackId = computed(() => activePack.value?.id || committeePacks[0]?.id || '')
const filteredCommitteePresets = computed(() =>
  committeePresets.filter((preset) => preset.packId === activePackId.value)
)
const activePresetId = computed(() =>
  committeePresets.find((preset) =>
    preset.mode === selectedMode.value
    && preset.roleIds.length === selectedRoleIds.value.length
    && preset.roleIds.every((id) => selectedRoleIds.value.includes(id))
  )?.id || null
)

const canSubmit = computed(() =>
  inputText.value.trim().length > 0
  && selectedRoleIds.value.length > 0
  && appStore.discussSelectedModels.length > 0
)

const renderedSynthesis = computed(() => md.render(store.phase3Content))
const roleAssignmentPreview = computed(() =>
  buildRoleModelAssignments(selectedRoleIds.value, appStore.discussSelectedModelObjects)
)
const assignmentMap = computed(() =>
  Object.fromEntries(roleAssignmentPreview.value.map((item) => [item.roleId, item]))
)

const phaseNames: Record<CommitteePhase, string> = {
  1: '角色独立发言',
  2: '第二轮回应',
  3: '委员会汇总',
}

function toggleRole(roleId: string) {
  const index = selectedRoleIds.value.indexOf(roleId)
  if (index === -1) {
    selectedRoleIds.value = [...selectedRoleIds.value, roleId]
    return
  }
  selectedRoleIds.value = selectedRoleIds.value.filter((id) => id !== roleId)
}

function selectAllRoles() {
  selectedRoleIds.value = COMMITTEE_ROLES.map((role) => role.id)
}

function clearRoles() {
  selectedRoleIds.value = []
}

function selectCommitteePack(packId: string) {
  selectedPackId.value = packId
}

function applyCommitteePreset(presetId: string) {
  const preset = committeePresets.find((item) => item.id === presetId)
  if (!preset) return
  selectedPackId.value = preset.packId
  selectedRoleIds.value = [...preset.roleIds]
  selectedMode.value = preset.mode
}

function isCategoryFullySelected(category: RoleCategoryId) {
  return COMMITTEE_ROLES
    .filter((role) => role.category === category)
    .every((role) => selectedRoleIds.value.includes(role.id))
}

function toggleCategory(category: RoleCategoryId) {
  const ids = COMMITTEE_ROLES
    .filter((role) => role.category === category)
    .map((role) => role.id)

  if (ids.every((id) => selectedRoleIds.value.includes(id))) {
    selectedRoleIds.value = selectedRoleIds.value.filter((id) => !ids.includes(id))
    return
  }

  selectedRoleIds.value = Array.from(new Set([...selectedRoleIds.value, ...ids]))
}

async function handleSubmit() {
  if (!canSubmit.value) return

  await store.startDiscuss({
    promptText: inputText.value.trim(),
    modelPool: appStore.discussSelectedModelObjects,
    mode: selectedMode.value,
    roleIds: selectedRoleIds.value,
  })
}

function startNew() {
  inputText.value = ''
  store.clearSession()
}

function continueToChat() {
  appStore.copySelection('discuss', 'chat')
  router.push('/chat')
}

function handleKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault()
    handleSubmit()
  }
}
</script>
