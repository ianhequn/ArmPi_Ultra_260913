# 幻尔机械臂控制 — 移植工作计划

> 索引：[`pi_project_mem.md`](pi_project_mem.md)（项目枢纽）

---

## 0. 原则与决策

- **沿用原包名**；**全保留、源码逻辑不动**，仅做"能编译/能启动"的**接线级**改动。
- Q1 全保留｜Q2 保留 `FollowJointTrajectory`（装 `ros-jazzy-control-msgs`）｜Q3 串口设备/波特率做成 ROS 参数｜Q4 硬件随时可接。

---

## 1. 阶段总览

| 阶段 | 包 | 主要工作 | 验收 |
|---|---|---|---|
| 1 | `ros_robot_controller_msgs` | 复制 msg/srv + 构建配置 | `colcon build` 通过 + `ros2 interface show` |
| 2 | `ros_robot_controller` | 复制 node+sdk+launch；适配 Jazzy；参数化串口 | 编译通过；**接板读舵机 ID** |
| 3 | `servo_controller_msgs` | 复制 msg | `colcon build` 通过 |
| 4 | `servo_controller` | 复制节点+config+launch | 编译通过；话题存在；发脉宽舵机动 |
| 5 | 联调 | bringup；范式 A/B | 端到端发指令可动 |
| 6 | 收尾 | udev / 文档 / 记忆库 / git | 归档 |

---

## 2. 各阶段任务

**阶段 1｜`ros_robot_controller_msgs`**
- 复制 `ROS/src/driver/ros_robot_controller_msgs/` 的 `msg/`、`srv/`、`CMakeLists.txt`、`package.xml`。
- 验收：编译通过；`ros2 interface show ros_robot_controller_msgs/msg/ServosPosition`。

**阶段 2｜`ros_robot_controller`（驱动，关键）**
- 复制 node + sdk + launch + scripts。
- 适配：**参数化串口**（设备/波特率，原写死 `/dev/ttyUSB0`、`1000000`）；去 `need_compile`/绝对路径。
- 验收 A（无板）：编译 + 节点能起。
- 验收 B（有板）：`get_state`/`check_servo_connection` 能读到舵机 ID → 协议正确。

**阶段 3｜`servo_controller_msgs`**
- 复制 msg + 构建配置；编译通过。

**阶段 4｜`servo_controller`（网关）**
- 复制 `controller_manager.py`、`servo_controller.py`、`joint_position_controller.py`、`bus_servo_control.py`、`joint_trajectory_action_controller.py`、`config/servo_controller.yaml`、`launch/`。
- 适配：去 `need_compile`/绝对路径；launch 不启动 `grasp`。
- 验收：`/controller_manager/servo_states` 存在；发脉宽舵机动。

**阶段 5｜联调**：bringup 两个节点；范式 A（直发脉宽）与 B（发关节角）各验一次。

**阶段 6｜收尾**：udev 按本机用户调整；更新枢纽与记忆库；git 提交。

---

## 3. 必需的最小改动清单（非重构）

1. `ros_robot_controller_msgs/CMakeLists.txt`：删 `rosidl_generate_interfaces` 里的**空字符串条目**。
2. launch：补 `get_package_share_directory` 的 import；去 `need_compile` + 写死 `/home/ubuntu/...`。
3. `servo_controller` launch：**不启动 `grasp`**（依赖未移植的 `kinematics`）。
4. 串口参数化（Q3）：动 `Board()` 传参处。
5. 依赖：安装 `ros-jazzy-control-msgs`（Q2）。

---

## 4. 风险与对策

| 风险 | 对策 |
|---|---|
| 无硬件 | 仅做到编译通过，通信验收挂起 |
| IK `.so` 为 aarch64 | 本计划**排除笛卡尔**；仅关节/脉宽 |
| 串口权限/时序 | dialout/udev；先单舵机试探 |
| Python 3.10→3.12 | 编译报错时逐条处理 |

---

## 5. 进度

- [x] 阶段 0 准备（决策定稿）
- [x] 阶段 1 `ros_robot_controller_msgs`
- [ ] 阶段 2 `ros_robot_controller`
- [ ] 阶段 3 `servo_controller_msgs`
- [ ] 阶段 4 `servo_controller`
- [ ] 阶段 5 联调
- [ ] 阶段 6 收尾
