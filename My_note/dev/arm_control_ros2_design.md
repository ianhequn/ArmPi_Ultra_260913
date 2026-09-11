# ROS2 代码组织方案：姿态/关节 → 串口

> 索引：[`pi_project_mem.md`](pi_project_mem.md)（项目枢纽）
> 目标：实现"姿态/关节信息 → 串口指令"的整条转换链；
> 形态上**保留原有两个包**以方便移植；代码组织**符合 ROS2 哲学**。
> 阅读顺序：看 §0 结论 → §2 目录树 → §3 三环分层 → §4 契约 → §6 对照表。

- 相关：`My_note/dev/arm_control_components.md`（组件模型）、`arm_control_port_notes.md`（移植范围）
- 创建 / 更新：2026-09-11

---

## 0. 结论（一句话）

用**两个包、每包三层环**的组织：

- **包 = 一个职责**：`arm_controller`(语义) / `arm_driver`(硬件)；接口独立成 `arm_msgs`。
- **包内三环**：`core`(纯逻辑，无 ROS) → `adapter`(适配) → `node`(薄外壳)。
- 两个包之间只通过**一个稳定话题**（脉宽指令）耦合。

```
姿态/关节 ──▶ [arm_controller] ──脉宽话题──▶ [arm_driver] ──串口──▶ STM32
              语义层                          硬件层
```

---

## 1. 为什么保留两个包（且这样更符合 ROS2）

| 理由 | 说明 |
|---|---|
| 职责分离 | "机器人语义"（关节/限位/单位）与"设备驱动"（协议/串口）是两类变化原因，ROS2 强调单一职责。 |
| 与官方架构同构 | 类似 `ros2_control` 的 "controller(算法) + hardware_interface(硬件)" 分层。 |
| 移植方便 | 原工程本就是这两个包，文件可近乎平移，diff 清晰。 |
| 可替换 | 换硬件只改 `arm_driver`；换机器人只改 `arm_controller`。 |

> 若强行做成"一个大节点"，短期省事，但会把两类变化原因焊死，违反 ROS2 的可组合/可替换原则。

---

## 2. 目标目录结构（推荐）

> 包名先用 `arm_*`；若首批要"零改名移植"，可暂时沿用 `servo_controller` / `ros_robot_controller`（见 §5）。

```
src/
├── arm_msgs/                        # ① 接口契约包 (ament_cmake + rosidl)
│   ├── msg/
│   │   ├── ServoCommand.msg         # duration + ServoCommandItem[]
│   │   ├── ServoCommandItem.msg     # id + position(pulse)
│   │   └── ServoStateArray.msg      # 反馈
│   ├── srv/
│   │   └── GetServoState.srv
│   ├── CMakeLists.txt
│   └── package.xml
│
├── arm_driver/                      # ② L1 硬件驱动 (ament_python)
│   ├── arm_driver/
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── protocol.py          # 纯: 组帧/解析/CRC8
│   │   │   └── transport.py         # 抽象传输: Serial / Mock
│   │   ├── board.py                 # 组合 protocol+transport, 暴露 bus_servo_*
│   │   └── driver_node.py           # 薄 ROS 外壳
│   ├── config/driver.yaml
│   ├── launch/driver.launch.py
│   ├── test/test_protocol.py
│   └── package.xml / setup.py
│
└── arm_controller/                  # ③ L2 语义网关 (ament_python)
    ├── arm_controller/
    │   ├── __init__.py
    │   ├── core/
    │   │   ├── joint_model.py       # 纯: pulse<->rad, 限位, 方向
    │   │   └── command_mapper.py    # 纯: JointState/姿态 -> ServoCommand
    │   ├── (ik.py)                  # 纯(可选): 姿态->关节; 当前受阻
    │   └── controller_node.py       # 薄 ROS 外壳
    ├── config/controller.yaml
    ├── launch/controller.launch.py
    ├── test/test_joint_model.py
    └── package.xml / setup.py

└── bringup/                         # ④ 装配层（只写 launch，不写算法）
    └── launch/arm_bringup.launch.py
```

---

## 3. 每个包内部 = 三环分层（核心思想）

这是让代码"既好移植又工程化"的关键：**按"是否依赖 ROS / 是否依赖硬件"分环**。

```
        ┌─────────────────────────────────────────┐
   node │  ROS 外壳：参数声明 / 接口注册 / 转换   │  ← 薄，只做粘合
        ├─────────────────────────────────────────┤
 adapter│  适配：消息<->领域对象, 传输实现         │  ← 可 Mock
        ├─────────────────────────────────────────┤
   core │  纯逻辑：数学 / 协议 / 状态机            │  ← 无 rclpy, 无 serial, 可单测
        └─────────────────────────────────────────┘
```

### 3.1 `arm_controller` 三环

| 环 | 文件 | 职责 | 依赖 |
|---|---|---|---|
| core | `joint_model.py` | 脉宽↔弧度、限位、方向 | 仅 math |
| core | `command_mapper.py` | 关节/姿态 → `ServoCommand`(脉宽) | 仅 core |
| core | `ik.py`(可选) | 笛卡尔姿态 → 关节 | 仅 math/numpy |
| node | `controller_node.py` | 订阅 `/arm/joint_command`、`/arm/pose_command`；调用 mapper；发布脉宽 | rclpy |

### 3.2 `arm_driver` 三环

| 环 | 文件 | 职责 | 依赖 |
|---|---|---|---|
| core | `protocol.py` | `AA55+CRC8` 组帧/解析/状态机 | 仅 struct |
| core | `transport.py` | `open/read/write/close` 抽象 + Serial/Mock | pyserial(仅 Serial) |
| mid | `board.py` | 组合，暴露 `bus_servo_set_position()` 等 | core |
| node | `driver_node.py` | 订阅脉宽话题 → `board`；发布反馈/服务 | rclpy |

> 好处：`test_protocol.py` 不插硬件、不启 ROS 就能验证协议；`MockTransport` 可回放报文做仿真。

---

## 4. 接口契约（消息包独立，ROS2 惯例）

| 接口 | 类型 | 定义方 | 说明 |
|---|---|---|---|
| `/arm/joint_command` | `sensor_msgs/JointState` | 标准 | 首选：关节角(rad)，ROS2 原生 |
| `/arm/pose_command` | 自定义 `PoseCommand` | `arm_msgs` | 可选：笛卡尔姿态(需 IK) |
| `/arm/servo_command` | `arm_msgs/ServoCommand` | `arm_msgs` | L2→L1 的内部契约（脉宽） |
| `/arm/servo_state` | `arm_msgs/ServoStateArray` | `arm_msgs` | 反馈 |
| `get_servo_state` | `arm_msgs/GetServoState` | `arm_msgs` | 回读 |

**原则**：
- 能用标准消息就用标准消息（`JointState`、`JointTrajectory`）。
- 自定义只定义"语义明确"的最小字段，不放歧义（原工程的两个 `ServosPosition` 就是反面教材：同名不同义）。
- 接口包**不含逻辑**，只含 `.msg/.srv/.action` + 构建配置。

---

## 5. 原文件 → 新位置 映射（移植友好）

| 原文件（HuanEr） | 新位置 | 处理方式 |
|---|---|---|
| `ros_robot_controller_sdk.py` | `arm_driver/core/protocol.py` + `transport.py` + `board.py` | **拆环**：协议/传输/组合分离 |
| `ros_robot_controller_node.py` | `arm_driver/driver_node.py` | 瘦身：只留舵机相关接口 |
| `driver/sdk/sdk/hw_interfaces.py` | `arm_driver/core/transport.py` | 借其 `use_sim` 思路 |
| `joint_position_controller.py` | `arm_controller/core/joint_model.py` | 近乎原样搬 |
| `servo_controller.py` (ServoManager) | 并入 `controller_node.py` / `command_mapper.py` | 拆分职责 |
| `controller_manager.py` | `arm_controller/controller_node.py` | 拆分为薄外壳 |
| `config/servo_controller.yaml` | `arm_controller/config/controller.yaml` | 平移 |
| `joint_trajectory_action_controller.py` | `arm_controller/`(第二阶段) | 暂缓 |
| `kinematics/*.so` | `arm_controller/core/ik.py`(可选) | 受阻，需重写或换平台 |

**包名策略**（二选一）：
- **A 零改名**：先沿用 `servo_controller` / `ros_robot_controller` / `*_msgs`，仅重排内部目录 → diff 最小。
- **B 规范化**：改为 `arm_controller` / `arm_driver` / `arm_msgs` → 更清晰，但需同步 launch/依赖。

> 建议：**先 A 后 B**。先用原名把功能跑通，接口稳定后再改名（改名只动包名与 import）。

---

## 6. ROS2 哲学对照 Checklist

| ROS2 原则 | 本方案落地 |
|---|---|
| 接口即契约 | 独立 `arm_msgs` 包；对外只暴露 msg/srv/action |
| 单一职责 | 一个包一个职责；一个节点一个角色 |
| 薄节点 | node 只做参数/接口/转换，逻辑在 core |
| 组合优于堆叠 | 先两进程跑通；需要时再 composition（见 §7） |
| 配置即参数 | `config/*.yaml`，**显式 `declare_parameter` + 类型 + 校验** |
| 命名空间 | 节点私有接口用 `~/`；对外用稳定全局名 `/arm/...`；避免相对名歧义 |
| 生命周期 | 进阶用 `LifecycleNode` 管"开串口/自检/激活"（见 §7） |
| QoS 明确 | 指令=`reliable`，传感器上行=`sensor_data` |
| 可测试 | core 纯逻辑单测；transport 可 Mock；`launch_testing` 集成 |
| 错误可观测 | `diagnostic_msgs` 上报串口/舵机状态；指令看门狗 |

> 反面教材（原工程，勿学）：同名不同义消息、隐式自动声明参数、写死绝对路径、依赖 `need_compile`/`CHASSIS_TYPE`、同一驱动两份副本。

---

## 7. 进阶选项（按需启用，不一次做完）

1. **Lifecycle 节点**：`configure`→打开串口+自检，`activate`→开始收发；比原工程 `init_finish` 服务规范。
2. **Composition / 进程内通信**：Python 节点**不支持** `rclcpp` composition；若追求零拷贝/低延迟，把 `arm_driver` 用 C++ 写成 component，`arm_controller` 不变。
3. **ros2_control**：最"官方"的做法——`hardware_interface::SystemInterface` 插件 + `joint_trajectory_controller`。总线舵机 5 轴项目可直接用，但改动大。
4. **Trajectory / Action**：需要轨迹或与 MoveIt 对接时，加 `FollowJointTrajectory` action（依赖 `ros-jazzy-control-msgs`）。

---

## 8. 例程的两种最小范式（原有格式）

原工程 `example` 包给出两种最小写法，可直接照抄。

### 范式 A：直连驱动（最省事，不经过 servo_controller）

- 文件：`example/example/simple/include/bus_servo_node.py`
  - 节点名 `servo_control_demo`，可执行名 `bus_servo`
  - 发布 `ros_robot_controller_msgs/ServosPosition` → `/ros_robot_controller/bus_servo/set_position`
  - 等 `/ros_robot_controller/init_finish`
- launch：`example/example/simple/bus_servo.launch.py`
  - include `ros_robot_controller/launch/ros_robot_controller.launch.py` + 本节点
- **只依赖 `ros_robot_controller`**，代码量最少。

### 范式 B：经 servo_controller（+ 可选 IK）

- 文件：`example/example/simple/include/ik.py`（`fk.py` 类似）
  - 发布 `servo_controller_msgs/ServosPosition` → `/servo_controller`，`position_unit='pulse'`
  - 等 `/controller_manager/init_finish` 和 `/kinematics/init_finish`
  - IK 在节点内直接调 `.so`：`from kinematics.inverse_kinematics import get_ik` + `transform.angle2pulse`
- launch：`example/example/simple/ik.launch.py`
  - include `sdk/launch/armpi_ultra.launch.py`（一次拉起 ros_robot_controller + servo_controller + kinematics）+ 本节点

### 共同"原有格式"

1. 一个 app 节点：`create_publisher(...)` + `create_client(Trigger, '/xxx/init_finish').wait_for_service()`
2. 一个 launch：include 底层 launch + `Node(package=..., executable=...)`
3. `setup.py` 的 `console_scripts` 注册可执行名
4. （原工程坏味道）依赖 `need_compile` 环境变量与写死 `/home/ubuntu/...` 路径

### 对本项目的直接含义

- "姿态"= 关节/脉宽：走**范式 A**最省事（甚至不需要 servo_controller）。
- "姿态"= 笛卡尔位姿：走**范式 B**，但 IK 的 `.so` 是 aarch64，本机 x86 跑不了 → 需换平台或重写 IK。
- "接收姿态→发指令"的自定义节点，本质就是照抄上面范式里那个 app 节点。

## 9. 待定（需用户确认）

- 包名：先 A(原名) 还是直接 B(新名)？
- "姿态"是否包含笛卡尔位姿（决定是否要 `ik.py`）？
- 是否启用 Lifecycle / ros2_control / Action（决定复杂度）。
- 内部契约是否沿用 `ServosPosition`，还是新定义 `ServoCommand`？

## 10. 变更记录

| 日期 | 内容 |
|---|---|
| 2026-09-11 | 建立：两包 + 三环分层 + 接口契约 + 文件映射 + ROS2 对照。 |
| 2026-09-11 | 新增 §8：例程的两种最小范式；记录决策 D1/D2/D3（见 `pi_project_mem.md`）。 |
