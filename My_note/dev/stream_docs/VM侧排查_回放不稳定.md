# VM 侧排查记录：回放"没有动作 / 只执行一部分"

> 日期：2026-09-17 ｜ 回链：[`VM侧完成报告_下行回放.md`](VM侧完成报告_下行回放.md)
> 状态：**已定位并修复**

---

## 1. 根因

### A. 斜坡限速追不上录制的动作（主因，日志坐实）

```
downlink: ramp lagging joint2:  target  0.092 but sending  0.562   → 差 27°
downlink: ramp lagging joint2:  target -0.980 but sending -0.038   → 差 54°
downlink: ramp lagging r_joint: target -1.969 but sending -1.407   → 差 32°
```

旧默认 `step = min(0.15, 2.0/rate)` → 跟踪上限只有 **115~258 °/s**，
而手拖录制轻松超过 400 °/s → 回放**永久滞后**，动作被"拉平/截断"。

### B. `get_state` 请求叠加导致永久卡死

```
no measured frames for 7.0s while 1 client(s) connected: get_state not answering
```

`_read_frame` 用 `call_async` + `wait(0.5)`；超时后**下一 tick 又发新请求**。
服务端按 FIFO 匹配响应，客户端一直丢旧 future → 队列错位 → 永久卡住，**一帧都不推**。

### 排除项

- ✅ 看门狗（命令率 22.6 Hz，无 timeout）
- ✅ 录制数据完整
- ✅ 下发链路（硬件实测：下发 joint1 +0.10 rad，实测跟到 +0.093 rad ✓）

## 2. 修复（净减 ~100 行）

| 项 | 处理 |
| --- | --- |
| 斜坡限速 | **整块删除**：`limit_step` / `step_for_rate` / `max_step_rad` / `max_velocity_rad_s` / `_command_rad` / `_warn_lagging` |
| 下发方式 | **直通**：宿主机目标原样发到 `/servo_controller`，由舵机按 `duration`（=1/`poll_rate_hz`）自己插值 → 完全跟随录制 |
| 软限越界告警 | 删除（网关本来就会 clamp，属噪音） |
| `get_state` | **同时只允许一个请求在飞**（上一个没回来就不再发）+ `future.result()` 加 try |
| 保留 | `enable_downlink`(默认关)、看门狗、断连卸力、auto_engage、token、`no measured frames` 告警 |

## 3. 现在的行为

```
宿主机 {"cmd":"joints", names, q}  (22.6 Hz)
      ↓ 原样
/servo_controller (position_unit=rad, duration=1/poll_rate_hz)
      ↓ 网关换算+限幅 → 驱动 → STM32 → 舵机按 duration 插值
```

- 节点侧**不做任何限速** → 回放保真度 = 录制保真度
- 安全仍靠：看门狗（`watchdog_timeout=1.0`）、断连/超时卸力、`enable_downlink` 默认关、
  `_engage()` 上力连发两次
- ⚠️ 起手保护也一并移除：若宿主机第一帧动作离当前姿态很远，会**较快**地过去（不再渐进）

## 4. 仍未解决 / 待观察

1. `no measured frames` 若再出现 → 查 CH340（`SerialException: [Errno 5] I/O error`
   会让驱动节点直接死掉）、舵机电源、多实例抢串口。
2. 建议 `poll_rate_hz` 用 25（≈宿主机 fps）：一轮读 6 舵机要 35 ms，30 Hz 会让串口总线过载。
