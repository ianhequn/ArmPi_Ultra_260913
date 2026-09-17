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

## 4. 二次排查：`get_state` 永久卡死（真根因，已修）

### 现象
`no measured frames for 2.0s → 7.0s → 12.1s`（**单调增长、永不恢复**），
而 `downlink: 22.7 Hz state=ARMED` 一直正常；日志最后停在
`bus_servo_read_position: [223]`（第 4 个舵机，6 个里少 2 个）后**再无一行**。

### 根因（厂商 SDK `ros_robot_controller_sdk.py`）
```python
def bus_servo_read_and_unpack(self, servo_id, cmd, unpack):
    with self.servo_read_lock:
        self.buf_write(...)
        data = self.bus_servo_queue.get(block=True)   # ← 没有超时！
```
- **任何一次"响应没到" → 永久阻塞**，而且**持有 `servo_read_lock`**
- 之后所有读（同一调用里剩下的舵机、所有后续 `get_state`）**全部死等**
- → 状态服务永久瘫痪。所以是"死了"，不是"慢"

### 为什么"越改越不稳定"
| 因素 | 作用 |
| --- | --- |
| `enable_downlink` 打开 | 总线负载翻倍（读 30Hz×6 + 写 22.7Hz×6）→ 一次丢/错响应概率大增 |
| `bus_servo_queue` 是 `maxsize=1` + `put_nowait` | 回包**被静默丢弃**；读之前又不清残留 → 一次残留让之后每次读**错位一格**（位置变垃圾） |
| 无匹配校验 | 读会把别人的/残留的回包当成自己的 |

### 修复（4 处，都围绕"永不死锁"）
1. `bus_servo_read_and_unpack` **加 `timeout=0.3s`**，超时返回 `None`
   （所有调用方本来就判 `if state is not None`，天然兼容）
2. 发请求**前先清空 `bus_servo_queue`**（清掉残留/上次超时的回包）
3. 回包**按 `id`/`cmd` 匹配**，不匹配就丢弃继续等
4. `recv_task` 的解析段整体 `try/except`（接收线程死 = 永久卡死，不可接受）

### 实测证据
| 测试 | 结果 |
| --- | --- |
| 读不存在的 id99（= 模拟丢响应） | 修前永久阻塞 → 修后 **0.10s 返回 None** |
| 卡过之后再读 id6 | 修前永久读不到 → 修后 **0.01s 返回 497** |
| **20Hz 写 + 30Hz 读 连续 20 秒** | **0 次读超时、0 次 no measured frames** |
| 启动时读 6 个舵机 | 6 个真实位置、0 次超时 |

### 我上一轮的错误（已一并修）
`dataset_stream` 里加的 `_pending` 守卫"上一个没回来就不发新请求"，
把**可恢复的降级**变成了**硬永久卡死**。已加 3s 兜底：超过就丢弃重发。

## 5. 结案：为什么"某个数据集不行、另一个行"

现象：同一个可执行文件、同一套参数、同样 22.x Hz 下行，
**192307 能回放，212614 不行** → 变量不是代码，是**动作内容**。

### 排除：总线负载
把"当前角度"按不同频率回写（手臂**原地不动**），读 25Hz：

| 下行写入率 | 新增读超时 | 新增卡流 |
| --- | --- | --- |
| 20 Hz | 0 | 0 |
| 40 Hz | 0 | 0 |
| **77 Hz**（462 次/秒舵机写） | **0** | **0** |

→ 写得多/写得快**不触发**。两个数据集下行率又都是 22.x Hz → 这条对两者一样。

### 真凶：手臂**真的在动**（电流）
失败run 时间轴：
```
t=056.3 宿主机连上
t=060.08 armed (torque on)      ← 手臂第一次开始动
t=061.22 读 4 个舵机 OK
t=061.2x 第 5 个 → 死
t=063.77 no measured frames for 2.0s
```
**纯读 3.7 秒完全正常；一开始动，1.2 秒内就死。**

机制：舵机启动/加速 → **电流尖峰** → 电源瞬时跌落 → 串口链路抖动 →
那一次读的响应丢失 →（修前）`queue.get(block=True)` 永久阻塞 → 整条读路径死。

**数据集相关性**：212614 大概率**起手第一帧就离当前姿态很远**（或关节顶到机械限位**堵转**），
舵机一上来就全力；192307 动作轻、起手贴近当前姿态，电流平稳，不触发。

> 也解释了"以前正常"：以前不开 `enable_downlink`，就没有
> "第一条 joints 命令让手臂从当前姿态猛扑到录制起点"这一步。

### 修复效果：从"永久死"变成"抖一下"
| 场景 | 修前 | 修后（实测） |
| --- | --- | --- |
| 丢一次响应 | 永久阻塞 | **0.10s** 返回 `None` |
| 丢过之后继续读 | 永久读不到 | **0.01s** 正常 |
| **重放 212614** | 卡住 | ✅ **回放成功**（用户确认） |

### 若复发（残余风险）
- 根治靠**硬件**：舵机独立/更足量电源。
- 软件备选：**一次性起手对齐**（仅当第一帧离当前姿态超阈值时，用 2~3 秒平滑靠过去）；
  ⚠️ 只影响开头，不是逐周期限速，不会造成回放滞后。

## 6. 仍未解决 / 待观察

1. `no measured frames` 若再出现 → 查 CH340（`SerialException: [Errno 5] I/O error`
   会让驱动节点直接死掉）、舵机电源、多实例抢串口。
2. 建议 `poll_rate_hz` 用 25（≈宿主机 fps）：一轮读 6 舵机要 35 ms，30 Hz 会让串口总线过载。
