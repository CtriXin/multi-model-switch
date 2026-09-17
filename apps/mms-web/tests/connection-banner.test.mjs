import test from "node:test";
import assert from "node:assert/strict";
import {
  CONNECTION_FAILURE_THRESHOLD,
  initialConnectionHealth,
  recordConnectionFailure,
  recordConnectionSuccess,
  resolveActiveBanner,
} from "../src/connection-state.ts";

test("initial connection health starts clean with zero failures and no notice", () => {
  const health = initialConnectionHealth();
  assert.equal(health.consecutiveFailures, 0);
  assert.equal(health.showNotice, false);
});

test("first failure does not show notice and increments count", () => {
  let health = initialConnectionHealth();
  health = recordConnectionFailure(health);
  assert.equal(health.consecutiveFailures, 1);
  assert.equal(health.showNotice, false);
});

test("second failure does not show notice when threshold is 3", () => {
  let health = initialConnectionHealth();
  health = recordConnectionFailure(health);
  health = recordConnectionFailure(health);
  assert.equal(health.consecutiveFailures, 2);
  assert.equal(health.showNotice, false);
});

test("third failure reaches threshold 3 and triggers quiet notice", () => {
  let health = initialConnectionHealth();
  health = recordConnectionFailure(health);
  health = recordConnectionFailure(health);
  health = recordConnectionFailure(health);
  assert.equal(health.consecutiveFailures, 3);
  assert.equal(health.showNotice, true);

  // Subsequent failure keeps notice active
  health = recordConnectionFailure(health);
  assert.equal(health.consecutiveFailures, 4);
  assert.equal(health.showNotice, true);
});

test("intermediate success clears failure count and keeps notice suppressed", () => {
  let health = initialConnectionHealth();
  health = recordConnectionFailure(health);
  health = recordConnectionFailure(health);
  assert.equal(health.consecutiveFailures, 2);
  assert.equal(health.showNotice, false);

  // Connection recovered before threshold
  health = recordConnectionSuccess();
  assert.equal(health.consecutiveFailures, 0);
  assert.equal(health.showNotice, false);

  // Next failure starts back from 1
  health = recordConnectionFailure(health);
  assert.equal(health.consecutiveFailures, 1);
  assert.equal(health.showNotice, false);
});

test("success after reaching threshold clears notice and resets counter to zero", () => {
  let health = initialConnectionHealth();
  health = recordConnectionFailure(health);
  health = recordConnectionFailure(health);
  health = recordConnectionFailure(health);
  assert.equal(health.showNotice, true);

  // Connection recovered after notice was active
  health = recordConnectionSuccess();
  assert.equal(health.consecutiveFailures, 0);
  assert.equal(health.showNotice, false);
});

test("supports configurable failure threshold", () => {
  let health = initialConnectionHealth();
  // With threshold 2, second failure triggers notice
  health = recordConnectionFailure(health, 2);
  assert.equal(health.showNotice, false);
  health = recordConnectionFailure(health, 2);
  assert.equal(health.showNotice, true);
});

test("后台轮询成功不得清掉操作错误：操作失败仍然醒目", () => {
  // 1. 用户操作失败设置了错误信息
  let error = "恢复连接后，可再次发送同一请求";
  let health = initialConnectionHealth();

  // 操作失败时显示 error 横幅
  assert.equal(resolveActiveBanner(error, health), "error");

  // 2. 即使后台轮询连续失败达 3 次（连接健康处于报警状态）
  health = recordConnectionFailure(health);
  health = recordConnectionFailure(health);
  health = recordConnectionFailure(health);
  assert.equal(health.showNotice, true);
  // 操作失败红条仍然具有最高优先级，绝对不被安静重连条覆盖
  assert.equal(resolveActiveBanner(error, health), "error");

  // 3. 关键契约：后台轮询成功！
  // 按照 App.tsx 规范，load() 成功只更新连接健康，绝对不得清掉 error
  health = recordConnectionSuccess();
  assert.equal(health.showNotice, false);
  // error 保持原样未被清掉，横幅仍然醒目显示 "error"
  assert.equal(resolveActiveBanner(error, health), "error");

  // 4. 只有用户显式点击关闭按钮（或发起新操作），error 才被清空
  error = "";
  assert.equal(resolveActiveBanner(error, health), "none");
});

