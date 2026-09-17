# AGENTS.md

> 供 AI 编码会话**自动读取**。目标：让新会话快速掌握——本地文档在哪、云记忆怎么用、用户的工作流与偏好。

---

## 0. 一句话

`test_ws01` 是 **ROS2 (Jazzy)** 工作区；已从 `HuanEr` 工程**移植幻尔(Hiwonder)机械臂控制**（接口包 + 驱动 + 语义网关），其它节点可用话题/服务控制机械臂。

---

## 1. 新会话启动流程（建议顺序）

1. **先读用途总览**：`My_note/README.md`（本机所有用途 + 使用文档位置）。
2. **再读枢纽**：`My_note/dev/pi_project_mem.md`（= 用户哲学 + 文档索引 + 关键决策 + 记忆库用法）。
3. 按任务读对应文档（见 §3）。
4. 涉及**历史/偏好/决策**时，**先查云记忆库再回答**（见 §4）。
5. **改动前先说清计划**，用户确认后再动手。

---

## 2. 目录速览

```
test_ws01/
├── AGENTS.md                 # 本文件
├── src/                      # ROS2 包（唯一被 git 跟踪的代码区）
├── My_note/README.md         # **本机用途总览 + 使用文档位置**
├── My_note/dev/              # 本地文档/记忆（含枢纽 pi_project_mem.md）
│   ├── learn/                # 一步一步教程
│   ├── stream_docs/          # LeRobot 主机侧协议/报告
│   └── test/                 # 手动测试脚本
├── My_note/codex/            # Codex 工具文档摘录
└── build/ install/ log/      # colcon 产物（忽略）
```

---

## 3. 本地文档地图（`My_note/dev/`）

| 文档 | 内容 |
| --- | --- |
| `pi_project_mem.md` | **枢纽**：用户开发哲学 + 文档索引 + 关键决策 + 记忆库用法 |
| `代码组织结构.md` | 包/节点/模块 + 依赖 + 数据管线（mermaid 多视图） |
| `arm_control_port_notes.md` | 移植需求/范围、STM32 通信文件清单、例程范式 |
| `arm_control_components.md` | 组件模型：话题↔STM32 的包/节点、内部块、接口、数据流 |
| `arm_control_ros2_design.md` | ROS2 代码组织：两包 + 三环分层、契约、文件映射 |
| `草稿_幻尔机械臂控制底层部分设计.md` | 底层两节点 + 三话题（已对齐厂商） |
| `arm_control_port_plan.md` | 移植工作计划：阶段/验收/最小改动/风险/已知问题 |
| `test/` | 手动测试脚本（见其 README） |

---

## 4. 云记忆（阿里云百炼记忆库）

- skill：`~/.agents/skills/alibabacloud-bailian-memory`
- `user_id`：`u24_ros2_dev_01`
- `project_id`：`ae32f4cf20ca41deb1bfee85e7f272aa`
- `memory_library_id`：`89ff0fcfe3864dbc928541290fb78877`

**检索（先查再答）**
```bash
cd ~/.agents/skills/alibabacloud-bailian-memory
SKILL_SESSION_ID=<32位hex> python3 scripts/search_memory.py --user-id u24_ros2_dev_01 --query "..."
```

**新增（原文保存）**
```bash
SKILL_SESSION_ID=<32位hex> python3 scripts/add_memory_content.py \
  --user-id u24_ros2_dev_01 --content "..."
```

- API Key 由脚本自动读取，**勿硬编码/打印**；写操作前须确认 `user_id` 与内容。
- 约定：**新结论先回写本地文档，按需同步云记忆库**。

---

## 5. 工作流与行为约定（用户偏好，优先遵守）

- **背景/方法**：MCU/嵌入式；借鉴 MATLAB/Simulink 模型化；**组件化**（明确输入/输出/参数，逻辑与硬件分离，可复用/可替换/可单测）。
- **协作**：**先讨论清楚再动手**；分阶段执行，每步先说改动与验收。
- **效率**：**不要大范围读文件**，按思路定向 `grep`/定位。
- **文档**：**要精髓、少废话**；先结论后细节；用 mermaid 表达结构与管线。
- **ROS2 工程化**：包创建**必须用官方命令 `ros2 pkg create`**（不手工建目录）；构建配置用标准格式，`ament` lint 应全绿（移植的厂商 Python 可关闭风格门禁）。

---

## 6. 当前状态

- 移植阶段 1–6 **全部完成**，硬件已验证（脉宽 + 角度两种控制）。
- 可用接口：
  - `/servo_controller`（`ServoPosition`/`ServosPosition`，单位 `pulse`/`rad`/`deg`）
  - `/joint_controller`（`sensor_msgs/JointState`）——⚠️ 厂商回调有 bug，**勿用**
  - `/ros_robot_controller/bus_servo/set_position`（直接脉宽）
  - 反馈：`/controller_manager/servo_states`、`joint_states`；服务 `get_state`
- LeRobot 链路（`arm_lerobot_dataset_stream`）：上行实测角流 + 下行回放（`enable_downlink` 默认关）。
- 限位：`servo_controller.yaml` 软限已对齐舵机硬限（`0x32`）；joint4 为 −100°~+90°。
- 未移植（受限）：`kinematics`/IK（厂商 `.so` 为 aarch64，本机不可用）。

---

## 7. 硬件

- 主控板：幻尔 STM32，经 **CH340**（`1a86:7523`）。
- 稳定设备路径（零配置）：`/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`；波特率 `1000000`。
- 启动（可覆盖 device/baudrate）：
  ```bash
  ros2 launch ros_robot_controller ros_robot_controller.launch.py \
    device:=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
  ```
- ⚠️ CH340 在 VMware 下**反复开关**易报 `Input/output error` 甚至掉线：等几秒再启动，或拔插/在 VMware 重新连接。
