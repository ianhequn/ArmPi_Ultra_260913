# VM 侧完成报告（下行回放）

> 回链：[`lerobot下行控制协议与VM设计.md`](lerobot下行控制协议与VM设计.md) ｜ 日期：2026-09-14
> 状态：**✅ VM 侧已实现**（P4 真机联调待做）

---

## 1. 结论

- **宿主机侧代码无需改动**：你已有的 `{"cmd":"joints","names":[...],"q":[...]}` 直接可用。
- 同一条 TCP 连接双向；`enable_downlink` 默认 `false` → 录制零干扰。

## 2. VM 侧启动

```bash
# 录制（默认，零下发）
ros2 launch arm_lerobot_dataset_stream arm_lerobot_dataset.launch.py

# 回放/rollout（必须显式开启）
ros2 launch arm_lerobot_dataset_stream arm_lerobot_dataset.launch.py \
  enable_downlink:=true
```

## 3. 已实现

| 项 | 行为 |
|---|---|
| `{"cmd":"joints","names":[...],"q":[...]}` | 绝对弧度目标；**首条自动上力** |
| `arm` / `disarm` | 保持 / 卸力 |
| `stop`（可带 `release:true`） | 停止；可选卸力 |
| `ping` | 仅刷看门狗 |
| 限幅 | `max_step_rad=0.15`、`max_velocity_rad_s=2.0`；斜坡**从实测位置起步**，上力不猛冲 |
| 看门狗 | `watchdog_timeout=0.3`：静默超时 / 断连 → 停止 + 卸力；再发命令可恢复 |
| 频率 | 下行 **~28 Hz**（串口读 6 舵机 35ms 是硬上限） |
| 单位/顺序 | 弧度；以 `names` 为准（与 `action` 一致） |
| 多客户端 | 读广播；写 last-writer-wins |
| `token` | 可选，默认不校验 |

## 4. 与设计稿的差异

- 未实现 `interpolate` / `prefer_pulse`：舵机按 `duration` 自行插值，统一走 `rad`。
- 其余（双锁、看门狗、状态机、限幅）已落地。

## 5. 验证

- 单测：`colcon test` 全绿。
- 集成测试（假驱动，`My_note/dev/test/test_downlink_integration.py`）：零下发 / 上力 / 斜坡限幅 / 看门狗 / 断连 / 恢复，**13/13 通过**。

## 6. 宿主机侧注意

1. 回放期间**持续发命令**（帧间隔 < 0.3s）；30fps 远低于阈值，没问题。
2. 回放**开始前**把臂摆到与第一帧动作接近的位置（斜坡会保护，但仍建议）。
3. `joint3` 软限已修正为 `±120°`（原 `[-120°,0°]`），回放不再单边被裁。

## 7. 请求

真机跑一次 `lerobot-replay`（先用手动 smoke test 确认链路），把日志/现象反馈回来。
