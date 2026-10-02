# My_note — 本机用途与文档地图

> 机器定位：**ROS2 (Jazzy) 幻尔/Hiwonder 机械臂控制 + LeRobot 数据集采集/回放工作站**（x86_64 VM，Python 3.12，colcon）。
> 新会话请先读枢纽 [`dev/pi_project_mem.md`](dev/pi_project_mem.md)。

---

## 1. 用途总览

| # | 用途 | 状态 | 入口 |
| --- | --- | --- | --- |
| A | **ROS2 话题/服务控制机械臂**（其它节点下发姿态） | ✅ 硬件验证 | `/servo_controller`、`/joint_controller` |
| B | **宿主机经虚拟串口 ASCII 命令控制** | ✅ 硬件验证 | `arm_serial_bridge` |
| C | **上位机 VOFA+ 经 UDP(RawData ASCII) 双向控制** | ✅ UDP 联调 | `arm_vofaUDP_bridge` |
| D | **LeRobot 数据集采集（上行实测角度流）** | ✅ 已实现 | `arm_lerobot_dataset_stream` |
| E | **LeRobot 回放/推理（下行驱动，端口复用）** | ✅ 真机验证通过 | 同上 + `enable_downlink:=true` |
| F | **手动调试/测量脚本**（读舵机、手推测范围、集成测试） | ✅ | `dev/test/` |
| G | **文档与云记忆**（本地文档 + 阿里云百炼记忆库） | ✅ 23 条 | `dev/pi_project_mem.md` §5 |

---

## 2. 按用途查文档

### A. ROS2 话题/服务控制
```bash
ros2 launch ros_robot_controller ros_robot_controller.launch.py device:=/dev/ttyUSB0
ros2 launch servo_controller servo_controller.launch.py
```
- 可控接口：`/servo_controller`（`ServosPosition`，单位 `pulse`/`rad`/`deg`）、`/joint_controller`（`JointState`，**厂商实现有 bug，勿用**）、
  `/ros_robot_controller/bus_servo/set_position`（直接脉宽）
- 反馈：`/controller_manager/servo_states`、`/controller_manager/joint_states`；服务 `get_state`
- 文档：[`dev/代码组织结构.md`](dev/代码组织结构.md)、[`dev/arm_control_components.md`](dev/arm_control_components.md)、[`dev/草稿_幻尔机械臂控制底层部分设计.md`](dev/草稿_幻尔机械臂控制底层部分设计.md)

### B. 宿主机串口 ASCII 控制
```bash
ros2 launch arm_serial_bridge arm_serial_control.launch.py
```
- 文档：[`dev/宿主机串口控制方案.md`](dev/宿主机串口控制方案.md)

### C. VOFA+ UDP 控制
```bash
ros2 launch arm_vofaUDP_bridge arm_vofa_control.launch.py
```
- 命令：`PING` / `Q`(缓存) / `R`(实测) / `H`(回0) / `A <j> <deg> [T]` / `L`(卸力) / `E`(保持)
- 文档：[`dev/VOFA_UDP控制方案.md`](dev/VOFA_UDP控制方案.md)

### D/E. LeRobot 采集与回放
```bash
# 录制（手拖，卸力）
ros2 launch arm_lerobot_dataset_stream arm_lerobot_dataset.launch.py release_torque:=true
# 回放（宿主机下发动作）
ros2 launch arm_lerobot_dataset_stream arm_lerobot_dataset.launch.py enable_downlink:=true
```
- 宿主机连 `192.168.174.128:1348`（仅主机网），TCP 换行 JSON，**宿主机不装 ROS2**
- 📘 **包内专属 README（用法/协议/参数/日志判读/排障）**：[`../src/arm_lerobot_dataset_stream/README.md`](../src/arm_lerobot_dataset_stream/README.md)
- 文档：
  - 上行协议/用法：[`dev/lerobot数据集流协议.md`](dev/lerobot数据集流协议.md)
  - 下行协议/参数：[`dev/stream_docs/lerobot下行控制协议与VM设计.md`](dev/stream_docs/lerobot下行控制协议与VM设计.md)
  - **给宿主机侧的完成报告**：[`dev/stream_docs/VM侧完成报告_下行回放.md`](dev/stream_docs/VM侧完成报告_下行回放.md)

### F. 调试与测量脚本
```bash
python3 dev/test/read_servo_id.py            # 读舵机 ID
python3 dev/test/read_servo_state.py         # 读位置/电压/温度
python3 dev/test/probe_joint_range.py        # 卸力手推测机械范围 + 读硬限 0x32
python3 dev/test/demo_move.py                # 小幅摆动演示
python3 dev/test/monitor_servo_cmds.py       # 监控所有舵机指令
python3 dev/test/test_downlink_integration.py  # 下行集成测试（假驱动）
```
- 文档：[`dev/test/README.md`](dev/test/README.md)

### G. 学习教程与记忆
- 一步一步教程（11 章）：[`dev/learn/README.md`](dev/learn/README.md)
- 项目枢纽（哲学+索引+决策+记忆库用法）：[`dev/pi_project_mem.md`](dev/pi_project_mem.md)
- **厂商程序功能清单**：[`dev/HuanEr/`](dev/HuanEr/README.md)（帧协议 · SDK 42 方法 · ROS2 32 接口 · STM32 固件）
- 工具文档（Codex）：[`codex/`](codex/)

---

## 3. 目录地图

```
My_note/
├── README.md                # ← 本文件（用途总览）
├── dev/                     # 项目文档
│   ├── pi_project_mem.md    #   枢纽：哲学/索引/决策/记忆库（先读）
│   ├── 代码组织结构.md        #   包/节点/模块/数据管线（mermaid）
│   ├── 宿主机串口控制方案.md   #   用途 B
│   ├── VOFA_UDP控制方案.md    #   用途 C
│   ├── lerobot数据集流协议.md  #   用途 D/E
│   ├── arm_control_*.md     #   移植需求/组件/设计/计划
│   ├── HuanEr/              #   **厂商程序功能清单**（协议/SDK/ROS2节点/固件）
│   ├── learn/               #   一步一步开发教程 00~10 + README
│   ├── stream_docs/         #   宿主机侧协议文档 + VM 完成报告
│   └── test/                #   手动脚本 + README
└── codex/                   # Codex 工具文档摘录
```

---

## 4. 硬件与环境事实

| 项 | 值 |
| --- | --- |
| 主控板 | 幻尔 STM32，经 **CH340**（`1a86:7523`） |
| 机械臂串口 | `/dev/ttyUSB0` @ `1000000`（多设备时用 `/dev/serial/by-path/`） |
| 网络 | 仅主机网：VM `192.168.174.128` ↔ 宿主机 `192.168.174.1` |
| 关节映射 | `joint1..joint5, r_joint` ↔ 舵机 id `6,5,4,3,2,1`（joint3 反向） |
| 限位 | 软限已对齐舵机硬限（`0x32`）；joint4 收紧为 −100°~+90° |
| 接口频率 | 串口读 6 舵机一轮 35 ms（**~28 Hz 上限**） |

⚠️ CH340 在 VMware 下反复开关易报 `Input/output error`/掉线：等几秒再启动，或拔插重连。

---

## 5. 更新约定

1. 本文件只写**用途与文档位置**；细节放对应文档。
2. 新增用途/文档时，**同时更新本文件 §1/§2/§3 与枢纽 `dev/pi_project_mem.md`**。
3. 新结论先回写本地文档，按需同步百炼记忆库。
