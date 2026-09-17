import test from "node:test";
import assert from "node:assert/strict";
import {
  composerRuleFromForm,
  createdScheduleNotice,
  describeRule,
  intervalSecondsFromHours,
  remainingScheduleQuota,
  scheduleErrorMessage,
  scheduleRunState,
  skipNote,
  validateComposerForm,
} from "../src/bot-schedules.ts";

test("intervalSecondsFromHours converts hours to seconds for composer interval rules", () => {
  assert.equal(intervalSecondsFromHours(3), 10800);
  assert.equal(intervalSecondsFromHours(1), 3600);
  assert.equal(
    composerRuleFromForm({
      kind: "interval",
      onceDate: "2026-09-17",
      onceTime: "09:00",
      atLocalTime: "09:00",
      weekday: 0,
      intervalHours: 3,
    }).everySeconds,
    10800,
  );
});

test("validateComposerForm blocks intervals shorter than 5 minutes", () => {
  const invalid = validateComposerForm({
    kind: "interval",
    onceDate: "2026-09-17",
    onceTime: "09:00",
    atLocalTime: "09:00",
    weekday: 0,
    intervalHours: 2 / 60,
  });
  assert.match(invalid || "", /定时间隔最短 5 分钟/);
  assert.equal(
    validateComposerForm({
      kind: "interval",
      onceDate: "2026-09-17",
      onceTime: "09:00",
      atLocalTime: "09:00",
      weekday: 0,
      intervalHours: 1,
    }),
    null,
  );
});

test("describeRule covers the four kinds without ISO timestamps", () => {
  assert.equal(describeRule({ kind: "daily", atLocalTime: "09:00" }), "每天 09:00");
  assert.equal(describeRule({ kind: "weekly", weekday: 0, atLocalTime: "09:00" }), "每周周一 09:00");
  assert.equal(describeRule({ kind: "interval", everySeconds: 10800 }), "每 3 小时");
  assert.match(describeRule({ kind: "once", at: "2026-09-17T01:00:00.000Z" }), /一次 /);
  assert.doesNotMatch(describeRule({ kind: "daily", atLocalTime: "09:00" }), /T\d{2}:/);
});

test("scheduleRunState keeps the four states distinct and never calls a past nextRunAt overdue", () => {
  const now = new Date("2026-09-16T12:00:00.000Z");
  const base = {
    id: "sch_1",
    botId: "bot_1",
    prompt: "查机票",
    rule: { kind: "once", at: "2026-09-16T01:00:00.000Z" },
    timezone: "Asia/Singapore",
    overlapPolicy: "skip",
    lastTaskId: null,
    createdAt: "2026-09-16T00:00:00.000Z",
    updatedAt: "2026-09-16T00:00:00.000Z",
  };

  assert.equal(
    scheduleRunState(
      {
        ...base,
        enabled: true,
        nextRunAt: "2026-09-17T01:00:00.000Z",
        lastRunAt: null,
        lastSkip: null,
      },
      now,
    ).kind,
    "upcoming",
  );

  const held = scheduleRunState(
    {
      ...base,
      enabled: true,
      nextRunAt: "2026-09-16T01:00:00.000Z",
      lastRunAt: null,
      lastSkip: { reason: "paused", at: "2026-09-16T01:00:00.000Z", skipped: 0 },
    },
    now,
  );
  assert.equal(held.kind, "held");
  assert.equal(held.holdReason, "paused");
  assert.match(held.detail, /恢复后会补跑/);
  assert.doesNotMatch(held.label, /逾期/);

  const completed = scheduleRunState(
    {
      ...base,
      enabled: true,
      nextRunAt: null,
      lastRunAt: "2026-09-16T01:05:00.000Z",
      lastSkip: null,
    },
    now,
  );
  assert.equal(completed.kind, "completed");
  assert.equal(completed.label, "已执行完");

  const invalid = scheduleRunState(
    {
      ...base,
      enabled: false,
      nextRunAt: null,
      lastRunAt: null,
      lastSkip: { reason: "invalid", at: "2026-09-16T00:00:00.000Z", skipped: 0 },
    },
    now,
  );
  assert.equal(invalid.kind, "invalid");
  assert.equal(invalid.label, "记录损坏");

  const pastWithoutSkip = scheduleRunState(
    {
      ...base,
      enabled: true,
      nextRunAt: "2026-09-16T01:00:00.000Z",
      lastRunAt: null,
      lastSkip: null,
    },
    now,
  );
  assert.equal(pastWithoutSkip.kind, "upcoming");
  assert.doesNotMatch(pastWithoutSkip.label, /逾期/);

  const disabledFuture = scheduleRunState(
    {
      ...base,
      rule: { kind: "daily", atLocalTime: "09:00" },
      enabled: false,
      nextRunAt: "2026-09-17T01:00:00.000Z",
      lastRunAt: null,
      lastSkip: null,
    },
    now,
  );
  assert.equal(disabledFuture.kind, "disabled");
  assert.equal(disabledFuture.label, "已暂停");
  assert.doesNotMatch(disabledFuture.label, /待触发/);

  const disabledHold = scheduleRunState(
    {
      ...base,
      enabled: false,
      nextRunAt: "2026-09-16T01:00:00.000Z",
      lastRunAt: null,
      lastSkip: { reason: "paused", at: "2026-09-16T01:00:00.000Z", skipped: 0 },
    },
    now,
  );
  assert.equal(disabledHold.kind, "disabled");
  assert.equal(disabledHold.label, "已暂停");
  assert.match(disabledHold.detail, /恢复后会补跑/);

  const disabledInvalid = scheduleRunState(
    {
      ...base,
      enabled: false,
      nextRunAt: null,
      lastRunAt: null,
      lastSkip: { reason: "invalid", at: "2026-09-16T00:00:00.000Z", skipped: 0 },
    },
    now,
  );
  assert.equal(disabledInvalid.kind, "invalid");
  assert.equal(disabledInvalid.label, "记录损坏");
  assert.equal(disabledInvalid.detail, "这条定时读不出来，改规则或时区后再启用。");

  const heldBusy = scheduleRunState(
    {
      ...base,
      enabled: true,
      nextRunAt: "2026-09-16T01:00:00.000Z",
      lastRunAt: null,
      lastSkip: { reason: "busy", at: "2026-09-16T01:00:00.000Z", skipped: 0 },
    },
    now,
  );
  assert.equal(heldBusy.kind, "held");
  assert.equal(heldBusy.holdReason, "busy");
  assert.match(heldBusy.detail, /恢复后会补跑/);

  const errorState = scheduleRunState(
    {
      ...base,
      enabled: true,
      nextRunAt: "2026-09-16T01:00:00.000Z",
      lastRunAt: null,
      lastSkip: { reason: "error", at: "2026-09-16T01:00:00.000Z", skipped: 0 },
    },
    now,
  );
  assert.equal(errorState.kind, "error");
  assert.equal(errorState.label, "上次没能建出任务");

  const gatedUpcoming = scheduleRunState(
    {
      ...base,
      rule: { kind: "daily", atLocalTime: "09:00" },
      enabled: true,
      nextRunAt: "2026-09-17T01:00:00.000Z",
      lastRunAt: null,
      lastSkip: null,
    },
    now,
    { wakeEnabled: false },
  );
  assert.equal(gatedUpcoming.kind, "gated");
  assert.equal(gatedUpcoming.label, "被总闸拦住");
  assert.doesNotMatch(gatedUpcoming.label, /待触发/);
});

test("skipNote explains missed counts without inventing a backlog for repeating rules", () => {
  const now = new Date("2026-09-16T12:00:00.000Z");
  assert.match(
    skipNote(
      {
        id: "sch_1",
        botId: "bot_1",
        prompt: "x",
        rule: { kind: "daily", atLocalTime: "09:00" },
        timezone: "Asia/Singapore",
        enabled: true,
        overlapPolicy: "skip",
        nextRunAt: "2026-09-17T01:00:00.000Z",
        lastRunAt: null,
        lastTaskId: null,
        lastSkip: { reason: "missed", skipped: 3 },
        createdAt: "",
        updatedAt: "",
      },
      now,
    ),
    /错过 3 次/,
  );
});

test("quota and backend error mapping include the 20-cap copy", () => {
  assert.equal(remainingScheduleQuota(18), "");
  assert.match(remainingScheduleQuota(19), /还能再加 1 条/);
  assert.match(remainingScheduleQuota(20), /最多 20 条定时/);
  assert.match(scheduleErrorMessage("SCHEDULE_LIMIT", "x", 20), /最多 20 条定时/);
  assert.match(scheduleErrorMessage("SCHEDULE_INTERVAL_TOO_SHORT", "x"), /最短 5 分钟/);
});

test("createdScheduleNotice distinguishes a past once from a future next run", () => {
  const now = new Date("2026-09-16T12:00:00.000Z");
  const past = createdScheduleNotice(
    {
      id: "sch_1",
      botId: "bot_1",
      prompt: "x",
      rule: { kind: "once", at: "2026-09-16T01:00:00.000Z" },
      timezone: "UTC",
      enabled: true,
      overlapPolicy: "skip",
      nextRunAt: "2026-09-16T01:00:00.000Z",
      lastRunAt: null,
      lastTaskId: null,
      lastSkip: null,
      createdAt: "",
      updatedAt: "",
    },
    () => "今天 09:00",
    now,
  );
  assert.match(past, /马上补跑一次/);
  const future = createdScheduleNotice(
    {
      id: "sch_2",
      botId: "bot_1",
      prompt: "x",
      rule: { kind: "daily", atLocalTime: "09:00" },
      timezone: "UTC",
      enabled: true,
      overlapPolicy: "skip",
      nextRunAt: "2026-09-17T01:00:00.000Z",
      lastRunAt: null,
      lastTaskId: null,
      lastSkip: null,
      createdAt: "",
      updatedAt: "",
    },
    () => "明天 09:00",
    now,
  );
  assert.equal(future, "已设定，下次 明天 09:00");
});
