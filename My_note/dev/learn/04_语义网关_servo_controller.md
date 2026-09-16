# 04 语义网关：servo_controller

> 目标：把"物理脉宽 0~1000"翻译成"关节名 + 弧度/角度"，并做限位。
> 对应代码：`src/servo_controller/`

---

## 它解决什么

驱动只认 `[[id, pulse]]`；上层想说的是"joint1 转 0.3 rad"。
网关负责：**命名映射 + 单位换算 + 限位 + 方向（flipped）**。

## 接口

| 类型 | 名字 | 说明 |
| --- | --- | --- |
| 订阅 | `/servo_controller` | `ServosPosition`，`position_unit` = `pulse`/`rad`/`deg` |
| 订阅 | `/joint_controller` | `sensor_msgs/JointState`（弧度） |
| 发布 | `/controller_manager/joint_states` | 指令值 |
| 发布 | `/controller_manager/servo_states` | 脉宽状态 |
| 服务 | `~/init_finish` | 就绪信号 |

## 配置（`config/servo_controller.yaml`）

```yaml
/**:
  ros__parameters:
    joint1:  {id: 6, init: 500, min: 0,    max: 1000}
    joint3:  {id: 4, init: 500, min: 1000, max: 500}   # min > max = 反向
    r_joint: {id: 1, init: 700, min: 0,    max: 1000}
```

---

## 步骤

### 1. 启动（先 driver 后网关）

```bash
# 终端 A
ros2 launch ros_robot_controller ros_robot_controller.launch.py
# 终端 B
ros2 launch servo_controller servo_controller.launch.py
```
预期：分别看到 `start` 日志。

### 2. 三种单位各发一条

```bash
# 脉宽
ros2 topic pub --once /servo_controller servo_controller_msgs/msg/ServosPosition \
  "{duration: 0.5, position_unit: 'pulse', position: [{id: 6, position: 600}]}"

# 角度
ros2 topic pub --once /servo_controller servo_controller_msgs/msg/ServosPosition \
  "{duration: 0.5, position_unit: 'deg', position: [{id: 6, position: 45.0}]}"

# JointState（弧度，用关节名）
ros2 topic pub --once /joint_controller sensor_msgs/msg/JointState \
  "{name: [joint1], position: [0.3]}"
```

### 3. 看反馈

```bash
ros2 topic echo /controller_manager/servo_states
ros2 topic echo /controller_manager/joint_states
```

---

## 原理（极简）

- `rad ↔ pulse` 按 `init / flipped / 量程` 换算（细节见 `joint_position_controller.py`）。
- `min > max` 表示该关节**方向反了**（joint3 就是）。
- 消息里的 `position_unit` 决定怎么解释数值，处理完统一转成 pulse 下发。

## 常见坑

- yaml 里的关节名必须和 `JointState.name` 一致，否则映射不上。
- 启动顺序：**先 driver，后网关**（网关要用 driver 的话题/服务）。
- 单位写错：`rad` 和 `deg` 搞混，会"只动一点"或"动很多"。
