# VM 侧排查记录：回放"没有动作 / 只执行一部分"

> 日期：2026-09-17 ｜ 回链：[`VM侧完成报告_下行回放.md`](VM侧完成报告_下行回放.md)
> 症状：录制数据完整，但回放不稳定（有时不动、有时只做一半）

---

## 1. 结论（已定位）

**根因 A：斜坡限速追不上录制的动作**（`ramp lagging` 已由日志坐实）

```
downlink: ramp lagging joint2: target 0.092 but sending 0.562
downlink: ramp lagging joint2: target -0.980 but sending -0.038   差 54°
downlink: ramp lagging r_joint: target -1.969 but sending -1.407   差 32°
```

旧默认 `step = min(0.15, 2.0/rate)` → 只有 **115~258 °/s** 的跟踪上限，
而手拖录制轻松超过 400 °/s → 回放**永久滞后**，动作被"拉平/截断"。

**已确认不是**：看门狗（命令率 22.6 Hz，无 timeout）、录制数据、下发链路
（实测：下发 joint1 +0.10 rad，实测跟到 +0.093 rad ✓）。

## 2. 本轮改动

| 项 | 内容 |
| --- | --- |
| `max_step_rad` | `0.15` → **`0.5`** |
| `max_velocity_rad_s` | `2.0` → `8.0` → **`15.0`** |
| 新增告警 | `ramp lagging <关节>: target .. but sending ..`（限速卡住） |
| 新增告警 | `<关节> target .. outside allowed [lo,hi] -> gateway WILL clamp it`（软限截断） |
| 新增告警 | `no measured frames for Ns while M client(s) connected: <原因>`（VM 不推流） |
| launch | `max_step_rad` / `max_velocity_rad_s` / `watchdog_timeout` / `release_*` 全部可传 |

> 新默认下跟踪上限：25 Hz → `min(0.5, 0.6)=0.5` rad/tick = **12.5 rad/s ≈ 716 °/s**；
> 30 Hz → 15 rad/s ≈ **859 °/s**。

## 3. 另一个"VM 不推流"的成因（顺手记录）

CH340 进入坏状态时驱动节点直接死掉：

```
serial.serialutil.SerialException: [Errno 5] could not open port /dev/ttyUSB0:
    [Errno 5] Input/output error
[ERROR] process has died
```

后果：`get_state` 服务不存在 → `dataset_stream` 一帧不推 → 宿主机"连上就没数据"。
新加的 `no measured frames ... driver service NOT available` 告警会直接点名。

## 4. 下一步

1. 重跑回放，`grep -E "ramp lagging|WILL clamp|no measured frames"`。
2. 仍有 `ramp lagging` → 继续加，例如
   `max_step_rad:=1.0 max_velocity_rad_s:=30.0`（≈ 无限制，完全靠 `duration` 插值跟随）。
3. 出现 `WILL clamp` → 是软限/机械范围问题（需决定是否放宽 yaml），不是速度问题。
4. 出现 `no measured frames` → 查串口/驱动（CH340 掉线、舵机电源、多实例抢串口）。
