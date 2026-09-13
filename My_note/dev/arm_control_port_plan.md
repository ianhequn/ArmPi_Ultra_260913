# 幻尔机械臂控制 — 移植工作计划

> 索引：[`pi_project_mem.md`](pi_project_mem.md)（项目枢纽）

---

## 0. 原则与决策

- **沿用原包名**；**全保留、源码逻辑不动**，仅做"能编译/能启动"的**接线级**改动。
- **包创建统一用官方命令 `ros2 pkg create`**，不手工建目录；构建配置用标准格式，保证 `ament` lint 全绿。
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

1. （阶段 1 已完成）`ros_robot_controller_msgs`：**用 `ros2 pkg create` 重建**；标准 CMakeLists/package.xml。
2. launch：补 `get_package_share_directory` 的 import；去 `need_compile` + 写死 `/home/ubuntu/...`。
3. `servo_controller` launch：**不启动 `grasp`**（依赖未移植的 `kinematics`）。
4. 串口参数化（Q3）：动 `Board()` 传参处。
5. 依赖：安装 `ros-jazzy-control-msgs`（Q2）。✅ 阶段 4 **运行时必需**（当前未装，`sudo` 需密码）。
6. 移植的厂商 Python 代码**关闭风格门禁**（删默认的 `test_flake8.py`/`test_pep257.py`），代码零改动。

---

## 4. 风险与对策

| 风险 | 对策 |
|---|---|
| 无硬件 | 仅做到编译通过，通信验收挂起 |
| IK `.so` 为 aarch64 | 本计划**排除笛卡尔**；仅关节/脉宽 |
| 串口权限/时序 | dialout/udev；先单舵机试探 |
| **CH340 在 VM 下会掉线** | 反复 open/close + EIO 会让 VMware 断开该 USB 设备（`/dev/ttyUSB0` 消失）。对策：温柔退出（勿 SIGKILL）、勿频繁开关、掉线后重新拔插/在 VMware 重新连接。**驱动已加容错+自动重连**：设备恢复后自动 `serial port reopened`，无需重启 launch；重连瞬间板子复位、机械臂回默认位（已接受）。实测偶发于 `L`/`E`（6 舵机扭矩命令）之后，指向 USB 模块接触/瞬态。 |
| Python 3.10→3.12 | 编译报错时逐条处理 |

### 厂商 bug（2026-09-13 更新）

**已修（硬件验证）：**
- `ros_robot_controller_sdk.py` `bus_servo_enable_torque`：**`0x0B`/`0x0C` 写反**（实测 `0x0B`=关扭矩、`0x0C`=开扭矩）→ 导致卸力失效。已对调。
- `ros_robot_controller_node.py` `get_torque_state`：调了不存在的 `bus_servo_read_torque`（应为 `bus_servo_read_torque_state`）→ 已修。
- `ros_robot_controller_sdk.py` `recv_task`/`buf_write`：串口 `SerialException` 未捕获会死线程/崩节点 → 已加容错 + 自动重连。

**未修（不影响使用）：**
- `pub_button_data` 用了未 import 的 `PacketReportKeyEvents` → 按键事件才 `NameError`。
- 节点退出重复 `rclpy.shutdown()` → 退出报错。

### 硬件验证记录（2026-09-11）

- 设备：`/dev/ttyUSB0`（CH340, `1a86:7523`），波特率 `1000000`。
- 直连 SDK：6 个舵机 ID（1~6）全部读到。
- ROS 节点 + 服务：`/ros_robot_controller/bus_servo/get_state` 正常，读到 `present_id=1`。
- **语义层联调**：启动驱动 + `servo_controller` launch；经 `/servo_controller` 发 `position_unit='deg'`，舵机 5：597 → 566（deg 16.3）→ 592（回原位）。

### 硬件验证记录（2026-09-13）

- **扭矩**：修正 0x0B/0x0C 后，`enable_torque(id,0)` → 读回 `[0]`（卸力）、`(id,1)` → `[1]`（保持）。
- **VOFA UDP 桥**：`L` 卸力、之后 `A` **自动恢复保持**、`E` 保持、`R` 读实测角度，均正常。
- **掉线**：USB 完整掉线（`/dev/ttyUSB*` 消失）需重新拔插；软件容错只能防崩，救不回不存在的端口。

### 串口设备路径处理（本项目采用零配置）

> ⚠️ 现有**两个同型号 CH340**（机械臂 + 宿主通信）。二者 `ID_SERIAL` 均为 `1a86_USB_Serial`（**无唯一序列号**）→ **`by-id` 名字冲突、不可用**（只生成一个，且当前指向宿主口）。**必须用 `by-path`**（绑定物理 USB 口）。

| 用途 | 路径（by-path，推荐） | 当前节点 | 验证 |
| --- | --- | --- | --- |
| **机械臂** | `/dev/serial/by-path/pci-0000:02:00.0-usb-0:2.1:1.0-port0` | `ttyUSB0` | `get_state` 读回 servo1 id=1 ✅ |
| 宿主通信 | `/dev/serial/by-path/pci-0000:02:00.0-usb-0:2.2:1.0-port0` | `ttyUSB1` | 无舵机响应 ✅ |

- 查找：`ls -l /dev/serial/by-path/`；`by-path` 随**物理 USB 口**变化（换口会变）。
- **本项目实操**：按顺序插（机械臂先→`ttyUSB0`，宿主口后→`ttyUSB1`），直接用 `/dev/ttyUSB0`、`/dev/ttyUSB1`，**无需 udev**；换口/顺序变了再改用 `by-path`。
- 单设备时 `by-id` 也可用；**多设备必须 by-path**（或用 udev 按 `ID_PATH` 分别建别名，如 `/dev/arm`、`/dev/hostlink`）。
- 厂商原规则：`KERNEL=="ttyACM0" / GROUP="ubuntu"` → 对本机**无效**。
- **launch 已支持参数**：`device`（默认 `/dev/ttyUSB0`）与 `baudrate`（默认 `1000000`）。覆盖示例：
  ```bash
  ros2 launch ros_robot_controller ros_robot_controller.launch.py \
    device:=/dev/ttyUSB0
  ```
- **话题控制实操**：经 `/ros_robot_controller/bus_servo/set_position` 驱动舵机 5：597 → 567（-30 脉冲 ≈ -7.2°）→ 回 597（实测 593）。

---

## 5. 进度

- [x] 阶段 0 准备（决策定稿）
- [x] 阶段 1 `ros_robot_controller_msgs`
- [x] 阶段 2 `ros_robot_controller`（✅ 硬件已验证：读到舵机 ID）
- [x] 阶段 3 `servo_controller_msgs`（✅ 编译 + 测试全绿）
- [x] 阶段 4 `servo_controller`（✅ 已移植 + 硬件联调：角度 deg → 脉宽 → 舵机）
- [x] 阶段 5 联调（✅ 范式 A 脉宽 + 范式 B 角度均实测）
- [x] 阶段 6 收尾（git `fa3dc17`；记忆库已同步；串口路径采用**零配置 by-id**，不用 udev）
