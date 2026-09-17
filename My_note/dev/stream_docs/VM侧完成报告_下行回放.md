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
ros2 launch arm_lerobot_dataset_stream arm_lerobot_dataset.launch.py release_torque:=true

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
| 限幅 | `max_step_rad=0.15`、`max_velocity_rad_s=8.0`（=344°/s，不成为回放瓶颈）；斜坡**从实测位置起步**，上力不猛冲 |
| 看门狗 | `watchdog_timeout=1.0`：静默超时 / 断连 → 停止 + 卸力；再发命令可恢复 |
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

---

## 8. 【新增】上行改为异步"最新帧"模型

目的：**允许宿主机任意修改 `dataset.fps`，VM 不再需要同步改 `poll_rate_hz`**。

### VM 侧变更

- 采样 tick **不再做网络 I/O**，只覆盖写"最新帧"槽位；每客户端一个独立发送线程。
- `sendall` 返回后取当前最新帧，**中间被跳过的帧直接丢弃**（不排队、不阻塞采样与下行控制）。
- 每连接 `SO_SNDBUF=2048`（有界）；`TCP_USER_TIMEOUT=10s` 先住死连接；发送端**不允许超时**（否则部分写入会撕坏 JSON 行）。
- 实测：客户端**完全不读** 4 秒，VM 采样仍稳定 **20/20 Hz**，客户端不被踢。

### 宿主机侧唯一需要做的事（一次性，很小）

读取时把**可读数据全部读空、只保留最后一行**：

```python
def recv_latest(sock):
    blob = b''
    while True:
        try:
            chunk = sock.recv(65536)
        except BlockingIOError:
            break
        if not chunk:
            return None
        blob += chunk
    return json.loads(blob.rstrip().split(b'\n')[-1])
```

如果不能改（或想先验证）：**只要 `poll_rate_hz` ≥ `fps` 也能工作**，但宿主机内核准的旧帧会逐步增多（延迟增长）。原因：TCP 无法回撤已发出的字节，只能暂存在宿主机内核的 `SO_RCVBUF`（Windows 默认 64KB ≈ 250 帧）。

### 结论

| 配置 | 结果 |
| --- | --- |
| 宿主机 drain + `poll_rate_hz ≥ fps` | ✅ 最佳：延迟 ≤1 帧 |
| 不 drain | ⚠️ 宿主机内积压（建议 drain） |
| `poll_rate_hz < fps` | 重复帧（无害） |
