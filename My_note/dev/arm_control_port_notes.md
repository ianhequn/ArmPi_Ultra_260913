# 机械臂控制移植 — 设计讨论与记忆

> 索引：[`pi_project_mem.md`](pi_project_mem.md)（项目枢纽）
> 本文件记录"从 HuanEr 移植机械臂控制"过程中**用户提出的要求、设计理念与关键决策**，
> 以及分析结论草案。属于持久记忆，跨会话保留。讨论阶段不落实现代码。

- 来源工程：`/home/u24/MyTest/dev01/ros2/HuanEr`
- 目标工程：`/home/u24/MyTest/dev01/ros2/test_ws01`
- 本文件：`My_note/dev/arm_control_port_notes.md`
- 创建：2026-09-11
- 最后更新：2026-09-11

---

## 1. 用户背景与设计理念（重要）

- 用户出身 **MCU / 嵌入式开发**。
- 借鉴 **MATLAB / Simulink 的模型化设计 (Model-Based Design)** 思想。
- 追求 **组件化开发 (Component-Based Development)**：
  - 模块应有明确的输入端口 / 输出端口 / 参数；
  - 硬件相关部分与算法/逻辑部分分离；
  - 关注可复用、可独立测试、可替换。
- 工作方式偏好：**先讨论清楚再动手**；不要擅自实现。

## 2. 本次需求定义（用户原话精神）

> 需要一个**节点**：**接收机械臂姿态信息**，并**向幻尔（Hiwonder）机械臂发送指令**。

- 目标产物：**单一节点**。
- 输入：机械臂姿态信息（"姿态"具体含义待确认，见 §4）。
- 输出：发送给幻尔机械臂的控制指令。
- 串口硬件：幻尔 STM32 控制板（原工程走 `/dev/ttyUSB0`，波特率 `1000000`，二进制协议 `AA 55 + CRC8`）。

## 3. 移植结论草案：移植 / 重写 / 丢弃

> 核心判断：**移植"驱动 + 协议 + 映射参数"，重写"节点外壳与 ROS 接口"，砍掉"视觉 / IK / 外设 / 轨迹"。**

| 组件（原工程位置） | 处置 | 理由 |
|---|---|---|
| `driver/ros_robot_controller/ros_robot_controller/ros_robot_controller_sdk.py` 的 `Board` 子集（组帧、CRC8、`bus_servo_set_position`、`bus_servo_read_position`、`bus_servo_read_id`、`enable_reception`） | **移植（最高优先级）** | 唯一硬件真值来源；协议正确性关键。属"驱动层"。 |
| `driver/servo_controller/servo_controller/joint_position_controller.py` | **移植** | 脉宽↔弧度、min/max 钳位、方向；纯数学，适合做成可单测纯模块（"参数/模型层"）。 |
| `driver/servo_controller/config/servo_controller.yaml` | **移植** | joint1..joint5 / r_joint 的 id/init/min/max，等价 Simulink Mask 参数。 |
| 消息语义 `ServosPosition`(ros_robot_controller_msgs / servo_controller_msgs)、`ServoState` | **移植并简化** | 两套重复定义需合并；只保留姿态指令所需字段。 |
| `ServoManager` 单位换算 + 钳位逻辑 | **移植并修正** | 逻辑可复用；按 Jazzy / 新接口改写。注意核对原 `joint_controller_callback` 的参数 bug。 |
| 关节状态回读 / `joint_states` 发布 | **按需移植** | 取决于是否要闭环反馈（见 §5-Q4）。 |
| `joint_trajectory_action_controller.py` + `controller_manager` | **暂不移植** | 属轨迹级功能，超出"单节点发指令"；且依赖 `ros-jazzy-control-msgs`（本机未安装）。 |
| `kinematics` / IK / `sdk` / `grasp` | **不移植** | `.so` 为 aarch64 + CPython3.10，本机 x86_64 + Py3.12 无法加载；无源码。属位姿级功能。 |
| `ros_robot_controller_node` 的 电机/步进/OLED/IMU/SBUS/蜂鸣器/电池/按键 | **不移植** | 机械臂用不到；且涉及串口独占问题（见 §5-Q2）。 |
| `app` / `peripherals` / `large_models` / 底盘 controller | **不移植** | 与本需求无关。 |

## 4. 目标节点内部结构（组件化视角）

```
输入端口: 机械臂姿态信息
   │
   ├─ ① 输入适配/校验            (ROS 外壳, 薄)
   ├─ ② 姿态 → 关节 → 脉宽 映射  (纯逻辑/参数, 可单测)
   │      含 单位换算 / 限位钳位 / 方向
   ├─ ③ 幻尔协议编码   AA55+CRC8 (驱动)
   └─ ④ 串口传输 (HAL 层, 可替换)
   │
输出端口: STM32 板 → 总线舵机
```

- 设计约束建议：②做成纯函数模块；④抽象成接口（真串口 / Mock / 文件回放），实现无硬件仿真与单元测试。
- ②的内容取决于"姿态"定义：关节角 → 仅映射；笛卡尔位姿 → 需要 IK（当前受阻）。

## 5. 待确认决策点

- **Q1 姿态信息定义**：(a) 关节角 `sensor_msgs/JointState`(rad) / (b) 舵机脉宽·角度 / (c) 末端笛卡尔位姿 `geometry_msgs/Pose`。→ (c) 需要 IK，当前受阻。
- **Q2 单节点 vs 板级网关**：STM32 串口是独占资源。单节点自持串口会使未来底盘/蜂鸣器/回读冲突。组件化更优做法是"网关独占串口 + 姿态节点 publish"。折中：先单节点，内部传输层独立以便日后拆分。
- **Q3 语言**：Python（复用 SDK、快） vs C++（与现有 `test_01_CH340` 一致、更嵌入式 HAL 风格，但需重写协议/CRC）。
- **Q4 开环/闭环**：仅发指令，还是也要回读舵机姿态做反馈。
- **Q5 可测试性是否作为硬约束**：纯逻辑与 ROS I/O 分离 + 传输层可 Mock/回放。

## 6. 环境事实（分析所得）

- 本机：**x86_64 / Ubuntu / ROS2 Jazzy / Python 3.12**。
- 原工程：Humble 时代、**aarch64**、Python 3.10。
- 已装：`pyserial 3.5`、`numpy 1.26.4`、`serial_driver`(Jazzy)。
- 未装：`control_msgs`（Jazzy 需 `ros-jazzy-control-msgs`）、`transforms3d`、`cv2`(待核)。
- 当前无 `/dev/ttyUSB*`、`/dev/ttyACM*`；`lsusb` 未见串口设备。
- 现有 `src/test_01_CH340` 为 **115200 波特 / ASCII**，与机械臂板的 **1000000 波特 / 二进制** 不匹配。

## 7. 与 STM32 主控板通信的源文件清单（分析所得）

### 7.1 真正打开串口 / 直接通信（核心）

| 文件 | 作用 |
|---|---|
| `ROS/src/driver/ros_robot_controller/ros_robot_controller/ros_robot_controller_sdk.py` | **唯一串口驱动**。`Board` 类：`serial.Serial` 打开 `/dev/ttyUSB0 @ 1000000`，组帧 `AA55+func+len+data+CRC8`。 |
| `ROS/src/driver/ros_robot_controller/ros_robot_controller/ros_robot_controller_node.py` | ROS 外壳：话题/服务 ↔ 串口帧；发布板子上报。 |
| `ROS/src/driver/ros_robot_controller/launch/ros_robot_controller.launch.py` | 启动上述节点。 |
| `ROS/src/driver/ros_robot_controller/scripts/99-ttyACM0.rules` + `create_udev_rules.sh` | 设备权限（CH340 `1a86:55d4`）。 |
| `ROS/src/driver/sdk/sdk/hw_interfaces.py` | 另一种 Board 封装（`serial_servo_*`、预留 `use_sim`）；**本仓库未 import**，可作组件化范式参考。 |
| `ros_robot_controller-ros2/src/ros_robot_controller/...` | 主仓库外的**独立副本**，默认设备 `/dev/ttyACM0`。 |
| `ROS/src/peripherals/scripts/99-ttyACM0.rules` | 同一块板 udev，额外 `SYMLINK+="rrc"`。 |

### 7.2 间接通信（走 ROS 话题/服务，最终汇到 board 节点）

- 舵机：`/ros_robot_controller/bus_servo/set_position` ← `driver/servo_controller`、`driver/kinematics`、`example/.../bus_servo_node.py`
- 底盘电机（**同一块板**）：`/ros_robot_controller/set_motor_speeds` ← `driver/controller/controller/mecanum.py`
- 其它：`set_led` / `set_buzzer` / `set_conveyor_speed` / `set_stepper_subdivision` / `move_stepper`
- 回读：`GetBusServoState` / `GetPWMServoState` 服务

### 7.3 STM32 端固件（被通信方，非上位机代码）

- `STM32/JetArmF4_Firmware/Hiwonder/Misc/packet.c/.h` — 协议解析（`0xAA 0x55`）
- `STM32/JetArmF4_Firmware/Hiwonder/System/packet_handle.c` — 命令分发
- `STM32/JetArmF4_Firmware/Hiwonder/Portings/packet_porting.c` + `packet_reports.h`
- `STM32/JetArmF4_Firmware/Hiwonder/Peripherals/serial_servo.c` — 总线舵机
- `STM32/JetArmF4_Firmware/Core/Src/usart.c` — USART1 @ 1000000

### 7.4 易混淆：非 STM32 的独立串口外设

- `wonderechopro_node.py` → `/dev/wonderechopro @115200`（语音模块）
- `large_models/.../speech/awake.py` → `/dev/ttyCH341USB0 @115200`（麦克风阵列）
- `peripherals/scripts/xf_mic.rules` → `ttyCH341USB*`

### 7.5 对设计的关键含义

1. 上位机侧只有**一条 UART 链路**，同一时刻只有一个进程能打开 → 谁持有串口，谁就是"板级网关"。
2. 源码里"驱动层"与"ROS 外壳"本就是两个文件，移植可沿此缝隙切分。
3. `hw_interfaces.py` 已示范"抽象硬件接口 + Mock/`use_sim`"的组件化写法，可直接借鉴。

## 8. 变更记录

| 日期 | 内容 |
|---|---|
| 2026-09-11 | 初始记录：用户背景/理念、需求、移植草案、待确认点、环境事实。 |
| 2026-09-11 | 新增 §7：与 STM32 主控板通信的全部源文件清单及设计含义。 |
