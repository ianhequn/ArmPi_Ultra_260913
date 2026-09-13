# PI 项目持久记忆（枢纽 / Hub）

> 唯一入口与索引：**用户哲学 + 文档链接 + 记忆库用法**。
> 新会话先读本文件；涉及历史/偏好先查百炼记忆库。长文放独立文档，独立文档回链本文件。

---

## 0. 元信息

| 项 | 值 |
| --- | --- |
| 项目 | test_ws01（ROS2 workspace） |
| 工作区根 | `/home/u24/MyTest/dev01/ros2/test_ws01` |
| 本文件 | `My_note/dev/pi_project_mem.md` |
| 环境 | ROS2 **Jazzy** / Python 3.12 / x86_64 / colcon |
| 现有包 | `ros_robot_controller[_msgs]`、`servo_controller[_msgs]`、`arm_serial_bridge`、`arm_vofaUDP_bridge`、`test_01_CH340`（C++，弃用） |
| 当前阶段 | **移植完成**（阶段 1–6）；新增：宿主机串口控制（方案） |
| 最后更新 | 2026-09-11 |

---

## 1. 用户开发哲学（优先遵守）

- **出身**：MCU / 嵌入式。
- **方法论**：MATLAB / Simulink 模型化；**组件化** —— 明确输入/输出/参数，逻辑与硬件分离，可复用、可替换、可单测。
- **工程化**：注重代码组织，按 **ROS2 方式**组织；**包创建必须用官方命令 `ros2 pkg create`**，不得手工建目录。
- **表达**：用"组件 / 组件里面有什么"的思维；**先结论后细节，降低阅读难度**。
- **协作**：**先讨论清楚再动手**。
- **效率**：**不大范围读文件**，按思路定向 grep。
- **文档**：**要精髓、少废话**。

---

## 2. 文档索引（`My_note/dev/`）

| 文档 | 内容 | 状态 |
| --- | --- | --- |
| [`arm_control_port_notes.md`](arm_control_port_notes.md) | 移植需求/范围、STM32 通信文件清单、例程范式 | ✅ |
| [`arm_control_components.md`](arm_control_components.md) | 组件模型：话题↔STM32 的包/节点、内部块、接口、数据流 | ✅ |
| [`arm_control_ros2_design.md`](arm_control_ros2_design.md) | ROS2 代码组织：两包 + 三环分层、契约、文件映射 | ✅ |
| [`草稿_幻尔机械臂控制底层部分设计.md`](草稿_幻尔机械臂控制底层部分设计.md) | 底层两节点 + 三话题（已对齐厂商） | ✅ |
| [`arm_control_port_plan.md`](arm_control_port_plan.md) | **移植工作计划**：阶段/任务/验收/最小改动/风险 | 🚧 执行中 |
| [`代码组织结构.md`](代码组织结构.md) | **代码组织**：包/节点/模块 + 依赖 + 数据管线（mermaid 多视图） | ✅ |
| [`宿主机串口控制方案.md`](宿主机串口控制方案.md) | 宿主机经虚拟串口发简单命令控制角度（**已实现+硬件联调**） | ✅ |
| [`VOFA_UDP控制方案.md`](VOFA_UDP控制方案.md) | 上位机 VOFA+ 经 UDP(RawData ASCII) 双向控制（**已实现、UDP 联调**） | ✅ |

> 阶段：**移植/编码**（阶段 1–4 完成且硬件已验证）。
> 其它位置：`My_note/codex/`（Codex 工具文档）。

---

## 3. 项目目标与关键决策

- **目标**：从 HuanEr 移植幻尔机械臂控制，让其它节点可下发指令；节点职责 = 接收姿态/关节 → 转串口指令给 STM32。
- **D1** 沿用原始包名（`servo_controller` / `ros_robot_controller` / `*_msgs`）。
- **D2** 最小工作量、按原有格式；不引入 Lifecycle / ros2_control / FollowJointTrajectory。
- **D3** 接口沿用原工程 `ServosPosition`。

---

## 4. 移植 TODO

- 顺序：`ros_robot_controller_msgs` → `ros_robot_controller` → `servo_controller_msgs` → `servo_controller`。
- 适配 Jazzy：`need_compile`、写死 `/home/ubuntu/...`、`find_packages()`。
- 先驱动层（串口/读舵机）→ 再网关层。
- 硬件确认：串口设备与波特率 `1000000`。
- 待定：姿态 = 关节角 或 笛卡尔位姿（决定是否需要 IK）。

---

## 5. 阿里云百炼记忆库（使用）

| 项 | 值 |
| --- | --- |
| skill | `~/.agents/skills/alibabacloud-bailian-memory` |
| `user_id` | `u24_ros2_dev_01` |
| `project_id` | `ae32f4cf20ca41deb1bfee85e7f272aa` |
| `memory_library_id` | `89ff0fcfe3864dbc928541290fb78877` |
| 已存条目 | 13 条：开发哲学 / 关键决策 / 控制架构 / 环境事实 / 底层设计草稿 / 移植计划 / 编码约定 / 移植完成 / 串口路径处理 / 宿主串口桥 / 串口设备识别 / VOFA UDP 桥 / VOFA RawData 粘连处理 |

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
- 约定：回答依赖历史/偏好时**先检索记忆库**；新结论先回写本地文档，按需同步记忆库。

---

## 6. 常用命令

```bash
cd /home/u24/MyTest/dev01/ros2/test_ws01
source /opt/ros/jazzy/setup.bash
colcon build --packages-select <pkg>
source install/setup.bash
ros2 run <pkg> <node>
ls -l /dev/ttyUSB* /dev/ttyACM*
ls -l /dev/serial/by-path/  # 多设备时用（按物理口，稳定）
ls -l /dev/serial/by-id/    # 仅单设备可靠（同型号 CH340 会冲突）
```

---

## 7. 更新约定（枢纽-辐条）

1. 本文件只放：**哲学 + 索引 + 决策 + 记忆库用法**。
2. 长文放独立文档并在此登记；独立文档顶部**回链本文件**。
3. 会话结束更新「待办/决策」与顶部「最后更新」。
