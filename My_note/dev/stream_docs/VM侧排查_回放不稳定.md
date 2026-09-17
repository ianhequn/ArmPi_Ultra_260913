# VM 侧排查记录：回放"没有动作 / 只执行一部分"

> 日期：2026-09-17 ｜ 回链：[`VM侧完成报告_下行回放.md`](VM侧完成报告_下行回放.md)
> 症状：录制数据完整，但回放不稳定（有时不动、有时只做一半）

---

## 1. 已排除

宿主机切下的日志显示：

```
downlink: 114 cmds in 5.0s (22.7 Hz) state=ARMED     ← 宿主机在稳定发
downlink SAFE: client disconnected                   ← 是宿主机主动断开
```

- ✅ 宿主机命令率 **22.7 Hz**（远高于看门狗），**没有** `watchdog timeout`
- ✅ VM 侧入队/状态机正常 → 下发频率不是瓶颈
- ✅ 录制数据完整（已确认）

## 2. 剩余嫌疑（两个，均可从日志直接看出）

| # | 嫌疑 | 机制 | 日志特征 |
| --- | --- | --- | --- |
| A | **斜坡限速追不上** | `step=min(max_step_rad=0.15, 8.0/25=0.32)=0.15` rad/tick = **3.75 rad/s = 215°/s**；手拖动作超过这个速度就永久滞后，动作被"拉平" | `downlink: ramp lagging jointX: target 1.200 but sending 0.780` |
| B | **yaml 软限 clamp** | 网关会把 `q` 限到关节 `[min,max]`。手拖时关节常被推到标定窗口外（实测 joint5 脉冲 −194…1194，远超 [0,1000]）→ 回放**走不到录制的位置** | `downlink: jointX target 1.800 rad outside allowed [-2.094, 2.094] -> gateway WILL clamp it` |

## 3. 本轮改动（可观测 + 可调）

### 3.1 新增两条告警（直接对应上面 A / B）

- `downlink: ramp lagging <关节>: target <x> but sending <y> (0.15 rad/tick = 215 deg/s max)`
  → 说明**限速**卡住，调大 `max_step_rad` / `max_velocity_rad_s`
- `downlink: <关节> target <q> rad outside allowed [lo, hi] -> gateway WILL clamp it`
  → 说明**软限**截断，是机械/标定范围问题，不是速度问题

### 3.2 参数可在 launch 直接改（以前改不了）

```bash
ros2 launch arm_lerobot_dataset_stream arm_lerobot_dataset.launch.py \
  enable_downlink:=true \
  max_step_rad:=0.5 max_velocity_rad_s:=8.0 watchdog_timeout:=1.0 \
  release_on_timeout:=true release_on_disconnect:=true
```

### 3.3 默认值放宽

| 参数 | 旧 | 新 | 理由 |
| --- | --- | --- | --- |
| `max_velocity_rad_s` | 2.0 (115°/s) | **8.0 (344°/s)** | 手拖动作轻松超过 115°/s |
| `watchdog_timeout` | 0.3 | **1.0** | 断连安全由断连路径保证，不靠看门狗 |

### 3.4 `_engage()` 上力连发两次

防止单帧丢失导致"全程无力"（表现为**完全没动作**）。

## 4. 下一步

1. 宿主机跑一次回放，把 `dataset_stream` 的告警行贴回来。
2. 若出现 `ramp lagging` → 调大 `max_step_rad`/`max_velocity_rad_s`。
3. 若出现 `WILL clamp` → 是软限（机械范围）问题，需决定是否放宽 yaml。
4. 若两者都没有但仍无动作 → 查宿主机发的是不是 `action` 列、以及 `teleop` 是否在同时写同一个端口。
