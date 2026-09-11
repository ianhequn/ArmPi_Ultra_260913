# 机械臂控制组件模型（话题 ↔ STM32 板之间）

> 索引：[`pi_project_mem.md`](pi_project_mem.md)（项目枢纽）
> 目标：用"组件 → 组件里有什么"的方式，讲清"话题通信"与"STM32 主控板"之间的**包和节点**。
> 低阅读难度：先看全景图，再看每个组件的接口/内部/文件。项目按 ROS2 方式组织。

- 相关文档：`My_note/dev/arm_control_port_notes.md`（移植范围与通信文件清单）
- 创建 / 更新：2026-09-11

---

## 0. 一句话答案

介于"话题"与"STM32 板"之间的，是 **2 个包、2 个节点**，外加 **2 个接口(message)包**：

| 层 | 包 (package) | 节点 (node) | 可执行名 | 角色 |
|---|---|---|---|---|
| L2 话题网关 | `servo_controller` | `controller_manager` | `servo_controller` | 把"关节/姿态指令"翻译成"舵机脉宽" |
| L1 硬件网关 | `ros_robot_controller` | `ros_robot_controller` | `ros_robot_controller` | 把"舵机脉宽"翻译成"串口帧" |
| 接口 | `servo_controller_msgs` | — | — | L2 对外消息 |
| 接口 | `ros_robot_controller_msgs` | — | — | L1/L2 之间消息 |

> 其余 `kinematics`、`grasp`、`app`、`example` 都在 **话题侧（更上层）**，不属于"之间"。

---

## 1. 全景图（从话题一路到板子）

```
   ┌─────────────────────────── 话题侧（业务/算法节点） ───────────────────────────┐
   │  发布 /servo_controller (ServosPosition, 可带 unit=pulse/rad/deg)             │
   │  发布 /joint_controller  (JointState)                                         │
   └───────────────────────────────┬───────────────────────────────────────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │ L2 话题网关组件：包 servo_controller                 │
        │     节点 controller_manager                          │
        │   内部：ServoManager / JointPositionController /     │
        │         JointTrajectoryActionController / 参数 yaml  │
        └──────────────────────────┬──────────────────────────┘
                                   │ topic: /ros_robot_controller/bus_servo/set_position
                                   │        (ros_robot_controller_msgs/ServosPosition, 脉宽 uint16)
        ┌──────────────────────────▼──────────────────────────┐
        │ L1 硬件网关组件：包 ros_robot_controller              │
        │     节点 ros_robot_controller                        │
        │   内部：Board (SDK) + ROS 外壳                       │
        └──────────────────────────┬──────────────────────────┘
                                   │ serial: AA 55 | func | len | data | CRC8 @ 1000000
        ┌──────────────────────────▼──────────────────────────┐
        │              STM32 主控板 (JetArmF4)                 │
        │        → 总线舵机 / 电机 / 蜂鸣器 / LED ...          │
        └─────────────────────────────────────────────────────┘
```

---

## 2. 组件 L2：`servo_controller`（话题网关）

**一个箱子 = 一个 ROS2 包**；对外是 1 个主节点，内部是若干模块。

### 2.1 节点

| 项 | 内容 |
|---|---|
| ROS2 包 | `servo_controller`（`ament_python`） |
| 节点名 | `controller_manager` |
| 可执行名 | `servo_controller`（入口 `controller_manager:main`） |
| 附带节点 | `grasp`（入口 `grasp:main`，高层抓取，属话题侧） |

### 2.2 对外接口（端口）

| 方向 | 类型 | 名称 | 消息/服务 |
|---|---|---|---|
| 入 | topic | `/servo_controller` | `servo_controller_msgs/ServosPosition`（`position_unit` = pulse/rad/deg） |
| 入 | topic | `/joint_controller` | `sensor_msgs/JointState` |
| 入 | action | `/arm_controller/follow_joint_trajectory` | `control_msgs/FollowJointTrajectory` |
| 入 | action | `/gripper_controller/follow_joint_trajectory` | `control_msgs/FollowJointTrajectory` |
| 入 | service 客户端 | `/ros_robot_controller/init_finish` | `std_srvs/Trigger` |
| 出 | topic | `/ros_robot_controller/bus_servo/set_position` | `ros_robot_controller_msgs/ServosPosition`（脉宽） |
| 出 | topic | `/controller_manager/servo_states` | `servo_controller_msgs/ServoStateList` |
| 出 | topic | `/controller_manager/joint_states` | `sensor_msgs/JointState` |
| 出 | service | `/controller_manager/init_finish` | `std_srvs/Trigger` |

### 2.3 内部有什么（模块清单）

| 模块（文件） | 职责 |
|---|---|
| `servo_controller.py` → `ServoManager` | 持有各舵机当前状态；接收脉冲指令并转发给 L1 |
| `joint_position_controller.py` → `JointPositionController` | 脉宽↔弧度换算、min/max 限位、方向翻转 |
| `joint_trajectory_action_controller.py` → `JointTrajectoryActionController` | 轨迹 action 执行 |
| `action_group_controller.py` → `ActionGroupController` | 播放 `.d6a` 动作组（可选） |
| `controller_manager.py` → `ControllerManager` | **节点主入口**：组装上述模块、建话题/服务、发布反馈 |
| `config/servo_controller.yaml` | 参数：`joint1..joint5`/`r_joint` 的 id/init/min/max；`arm_controller`/`gripper_controller` 分组 |

### 2.4 参数

来自 `config/servo_controller.yaml`（`declare_parameter` / 自动声明 override）。

---

## 3. 组件 L1：`ros_robot_controller`（硬件网关 / 驱动）

### 3.1 节点

| 项 | 内容 |
|---|---|
| ROS2 包 | `ros_robot_controller`（`ament_python`） |
| 节点名 | `ros_robot_controller` |
| 可执行名 | `ros_robot_controller` |

### 3.2 对外接口（端口）

| 方向 | 类型 | 名称（`~` = 节点私有） | 消息/服务 |
|---|---|---|---|
| 入 | topic | `~/bus_servo/set_position` | `ros_robot_controller_msgs/ServosPosition` |
| 入 | topic | `~/bus_servo/set_state` | `SetBusServoState` |
| 入 | topic | `~/pwm_servo/set_state`、`~/set_motor_speeds`、`~/set_led`、`~/set_buzzer`、`~/set_oled`、`~/set_conveyor_speed`、`~/set_stepper_subdivision`、`~/enable_reception` | 各种 msg |
| 入 | service | `~/bus_servo/get_state`、`~/pwm_servo/get_state`、`~/move_stepper`、`~/init_finish` | 各种 srv/Trigger |
| 出 | **串口** | `/dev/ttyUSB0 @ 1000000` | `AA 55 + func + len + data + CRC8` |
| 出 | topic | `~/imu_raw`、`~/battery`、`~/button`、`~/joy`、`~/sbus` | 板子上行数据 |

### 3.3 内部有什么（模块清单）

| 模块（文件） | 职责 | 层次 |
|---|---|---|
| `ros_robot_controller_sdk.py` → `Board` | **驱动层/HAL**：打开串口、组帧、CRC8、命令编解码、接收状态机 | 硬件 |
| `ros_robot_controller_node.py` → `RosRobotController` | **ROS 外壳**：话题/服务 ↔ `Board` 调用；发布上行数据 | 集成 |
| `launch/ros_robot_controller.launch.py` | 启动 | — |
| `scripts/99-ttyACM0.rules` | 串口权限（CH340） | — |

### 3.4 参数

`imu_frame`（默认 `imu_link`）。

---

## 4. 接口组件（消息定义，独立成包是 ROS2 惯例）

| 包 | 关键类型 | 归谁用 |
|---|---|---|
| `servo_controller_msgs` | `ServosPosition`(float32 position + `position_unit`)、`ServoState`、`ServoStateList`、`Grasp`、`Float64List` | L2 对外 |
| `ros_robot_controller_msgs` | `ServosPosition`(uint16 position)、`ServoPosition`、`BusServoState`、`SetBusServoState`、`GetBusServoCmd`、`GetBusServoState.srv` 等 | L1↔L2、L1 对外 |

> **注意：两个包都有 `ServosPosition`，但字段不同**（一个 float+单位，一个 uint16 脉宽）。
> 转换发生在 L2 的 `ServoManager` 里 —— 这正是"话题语义"与"硬件语义"的分界线。

---

## 5. 数据怎么流动

### 5.1 下行（发指令）

```
业务节点
  │ publish /servo_controller  (ServosPosition: unit=pulse/rad/deg)
  ▼
controller_manager (L2)
  │ 单位换算 + 限位  →  ServoManager
  │ publish /ros_robot_controller/bus_servo/set_position (pulse, uint16)
  ▼
ros_robot_controller (L1)
  │ Board.bus_servo_set_position(duration, [[id,pos],...])
  │ 组帧 AA55+CRC8
  ▼
串口 @1Mbps  →  STM32  →  总线舵机
```

### 5.2 上行（反馈）

```
STM32 → 串口帧 → Board 接收状态机 → ros_robot_controller
  │ (由 controller_manager 主动读 / 订阅)
  ▼
controller_manager 维护"当前姿态"
  │ publish /controller_manager/servo_states (ServoStateList)
  │ publish /controller_manager/joint_states (JointState)
  ▼
kinematics / 业务节点读取
```

---

## 6. ROS2 工程化组织建议（本项目采用）

1. **包按职责切分**：接口(msg) / 驱动(driver) / 业务(app) 三分离；一个包只干一件事。
2. **一个组件 = 一个包 = 一个主节点**；节点构造函数只做"组装 + 接口注册"。
3. **参数全部外置**：`config/*.yaml` + `declare_parameter`，代码里不写死。
4. **launch 分层**：顶层 bringup include 各组件 launch，不硬编码绝对路径（用 `get_package_share_directory`）。
5. **接口稳定优先**：对外只暴露 message/srv/action；驱动层 `Board` 不外泄。
6. **可测试性**：驱动层用"抽象接口 + Mock/`use_sim`"（参考 `driver/sdk/sdk/hw_interfaces.py` 的写法），保证无硬件也能跑。
7. **注意原工程的反面教材**（新项目应避免）：包重复副本（`ROS/src/...` 与 `ros_robot_controller-ros2/...`）、写死 `/home/ubuntu/...` 路径、依赖环境变量 `need_compile`/`CHASSIS_TYPE`。

---

## 7. 各层数据形态（笛卡尔位姿怎么处理？发到 STM32 的是占空比吗？）

> 答案：**不是占空比，是舵机位置 0~1000**。笛卡尔位姿在**主机**上就被消化完，STM32 见不到坐标。

| 层 | 数据形态 |
|---|---|
| 应用/算法 | 笛卡尔位姿 `[x,y,z]`(m) + `pitch`(°)（只有位置+俯仰，非完整 6D） |
| 主机 `kinematics` | 5 关节角度（deg/rad），可能多解 |
| 主机 `servo_controller` | 舵机位置 0~1000（消息里叫 `pulse`/脉宽） |
| 串口 → STM32 | 舵机 `id` + 位置 `0~1000` + 运行时间 `ms` |
| 总线 → 舵机 | 舵机自身位置协议（`serial_servo.c`，帧头 `0x55 0x55`） |
| 舵机内部 | 闭环控制（占空比只出现在这里） |

处理链：
```
[x,y,z,pitch] --get_ik(.so)--> 5关节角(多解) --择优--> --angle2pulse--> 位置0~1000
  --ServosPosition(pulse)--> /servo_controller --> /ros_robot_controller/...
  --board.bus_servo_set_position--> AA55帧 --> STM32 --> 总线舵机
```

关键事实：
- 串口帧：`AA 55 | 05 | len | 01 | dur(2B) | count | [id(1B) pos(2B)]... | CRC8`。
- `0~1000` 是**位置单位**（`RADIANS_PER_ENCODER_TICK = 240/360*2π/1000` → 1000 对应 240°，1 tick ≈ 0.24°，500 = 中位）。
- 机械臂用**总线舵机**：舵机自带闭环，上位机只发"目标位置 + 时间"。
- 占空比只在**直流电机**（底盘轮子，`set_motor_duty`/`set_motor_pwm`）出现，与舵机不是一回事。
- `position_unit='pulse'` 只是消息层叫法；`rad`/`deg` 最终也会换算回同一位置值。

### 7.1 心智模型：逐级收窄（不是并行汇入）

- **错误模型**：笛卡尔包与关节包并列，都发给串口包。
- **正确模型**：三级流水线，数据逐步收窄；笛卡尔必须先被 `kinematics` 消化成关节/脉宽，才可能下行。

| 级 | 组件（包） | 输入 | 输出 |
|---|---|---|---|
| 1 | `kinematics` | 笛卡尔位姿 | 关节角/脉宽 |
| 2 | `servo_controller` | 关节/脉宽/角度（单位可不同） | 脉宽 0~1000 |
| 3 | `ros_robot_controller` | 脉宽 | 串口字节 |

- 收敛接口：`/servo_controller`（`ServosPosition`，`position_unit` = pulse/rad/deg）。
- 捷径：范式 A 可直接发 `/ros_robot_controller/bus_servo/set_position`，**但只能送脉宽**，笛卡尔走不了。
- 到串口层时“只剩脉宽”，笛卡尔/关节概念已消失。
- **完整链路（仅当输入为笛卡尔时）**：笛卡尔位姿 → 关节角 → 脉宽 → 串口/STM32。
- **三种起点**：笛卡尔（走 IK）/ 关节角 rad·deg（跳过 IK）/ 脉宽（跳过前两级）。
- IK 可能多解，`kinematics` 会读当前舵机状态择优（转动量最小）→ 严格说是“笛卡尔 → 多组关节角 → 择优 → 一组 → 脉宽”。

### 7.2 app 实际入口统计（全仓核对）

| 证据 | 数量 |
|---|---|
| 调用 `bus_servo_control.set_servo_position()`（强制 `position_unit="pulse"`）的文件 | 40（app 9 + example 26 + large_models 5） |
| 创建 `ServosPosition` 发布者（发 `/servo_controller`）的文件 | 43 |
| 直发 `/ros_robot_controller/bus_servo/set_position` 的文件 | 1（仅 `bus_servo_node.py` demo） |
| 用 `position_unit='deg'` | 1 |
| 用 `position_unit='rad'` | 0 |

结论：**app 层入口几乎全是脉宽**；`/servo_controller` 是统一入口；`rad`/`deg` 基本闲置；直连串口驱动的只有最小 demo。

脉宽的四种来源：硬编码 / IK 计算 / `.d6a` 动作组 / 反馈闭环。

### 7.3 ROS2 审视：助手函数 vs 节点

- `bus_servo_control.set_servo_position()` **不是转换器**，只是“消息打包器”（把已给好的脉宽塞进 `ServosPosition` 并 publish）。
- 真正的“关节角→脉宽节点”是 `servo_controller`（支持 rad/deg），但 app 大多**在本进程内先转好脉宽**再用助手发出 → 转换发生在 app，而非节点。
- ROS2 味道不对的地方：
  1. `position_unit` 字符串变体字段 → “含多语义的消息”反模式；ROS2 偏好强类型、单一语义接口。
  2. 跨包共享 Python 助手 → 紧耦合，绕过节点边界；ROS2 偏“节点间用接口通信”。
  3. `ServosPosition.position` 用 float32 载脉宽 → 类型不贴切。
- 更 ROS2 的做法：`sensor_msgs/JointState`(rad) 作为输入契约，由节点内做映射；脉宽单独一个强类型话题。

---

## 8. 变更记录

| 日期 | 内容 |
|---|---|
| 2026-09-11 | 建立组件模型：L1/L2 网关包与节点、内部分块、接口、数据流、工程化建议。 |
| 2026-09-11 | 新增 §7：各层数据形态与“串口边界传什么”。 |
