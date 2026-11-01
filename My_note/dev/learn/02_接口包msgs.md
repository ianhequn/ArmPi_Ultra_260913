# 02 接口包 msgs

> 目标：看懂本项目的消息/服务，并能自己新建一个。
> 对应代码：`src/ros_robot_controller_msgs`、`src/servo_controller_msgs`

---

## 本项目真实的两个接口包

| 包 | 层次 | 主要内容 |
| --- | --- | --- |
| `ros_robot_controller_msgs` | 驱动层 | `ServosPosition`、`BusServoState`、`GetBusServoState.srv` 等 |
| `servo_controller_msgs` | 网关层 | `ServosPosition`、`ServoStateList`、`Grasp` 等 |

真实文件（节选）：

`ros_robot_controller_msgs/msg/ServosPosition.msg`
```
float64 duration
ros_robot_controller_msgs/ServoPosition[] position
```
`ros_robot_controller_msgs/msg/ServoPosition.msg`
```
uint16 id
uint16 position
```
`ros_robot_controller_msgs/srv/GetBusServoState.srv`（`---` 分隔请求/应答）
```
ros_robot_controller_msgs/GetBusServoCmd[] cmd
---
bool success
ros_robot_controller_msgs/BusServoState[] state
```

看真实定义：
```bash
cd /home/u24/MyTest/dev01/ros2/test_ws01
source /opt/ros/jazzy/setup.bash && source install/setup.bash
ros2 interface show ros_robot_controller_msgs/msg/ServosPosition
ros2 interface show servo_controller_msgs/msg/ServosPosition
```
注意：两个包都有 `ServosPosition`，但 `servo_controller_msgs` 的多了 `position_unit` 字段。

---

## 自己新建一个 msgs 包

消息/服务包用 **ament_cmake**。

### 1. 建包

```bash
cd /home/u24/MyTest/dev01/ros2/test_ws01/src
ros2 pkg create demo_msgs --build-type ament_cmake --dependencies std_msgs
```

### 2. 写 msg / srv

`msg/Point.msg`：
```
float64 x
float64 y
```
`msg/PointList.msg`（可嵌套其它 msg）：
```
float64 duration
demo_msgs/Point[] points
```
`srv/GetPoint.srv`：
```
uint8 index
---
float64 x
float64 y
```

### 3. 注册（`CMakeLists.txt`）

```cmake
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Point.msg"
  "msg/PointList.msg"
  "srv/GetPoint.srv"
)
```

### 4. `package.xml`

```xml
<build_depend>rosidl_default_generators</build_depend>
<exec_depend>rosidl_default_runtime</exec_depend>
<member_of_group>rosidl_interface_packages</member_of_group>
```

### 5. 构建 & 在节点里用

```bash
colcon build --packages-select demo_msgs
source install/setup.bash
```
```python
from demo_msgs.msg import PointList, Point

msg = PointList()
msg.duration = 0.5
p = Point()
p.x, p.y = 1.0, 2.0
msg.points.append(p)
```

---

## 原理（极简）

- msg/srv 是**接口定义（IDL）**，构建时生成各语言的类。
- `pkg/Type[]` 表示数组；`---` 分隔 srv 的请求/应答。
- 生成物在 `install/<pkg>/lib/python3.12/site-packages/<pkg>/`。

## 常见坑

- 消息包**必须先 build**，用它的包才 build 得过。
- 改了 `.msg` → 用到它的包都要重新 build。
- 类型要写对：`ros_robot_controller_msgs` 的 `position` 是 `uint16`，`servo_controller_msgs` 的是 `float32`。
