# 02 接口包 msgs

> 目标：自己定义消息/服务，并让节点能用上。
> 对应代码：`src/ros_robot_controller_msgs`、`src/servo_controller_msgs`

---

## 步骤

### 1. 建包（ament_cmake）

```bash
cd /home/u24/MyTest/dev01/ros2/test_ws01/src
source /opt/ros/jazzy/setup.bash
ros2 pkg create arm_demo_msgs --build-type ament_cmake --dependencies std_msgs
```

### 2. 写 message

`msg/ServoPosition.msg`：
```
uint16 id
uint16 position      # 0~1000
```

`msg/ServosPosition.msg`（**可以嵌套别的 msg**）：
```
float64 duration
arm_demo_msgs/ServoPosition[] position
```

### 3. 写 service

`srv/GetState.srv`：`---` 上面是**请求**，下面是**应答**。
```
uint8 id
---
uint16 position
```

### 4. 注册（`CMakeLists.txt`）

```cmake
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ServoPosition.msg"
  "msg/ServosPosition.msg"
  "srv/GetState.srv"
)
```

### 5. `package.xml`

```xml
<build_depend>rosidl_default_generators</build_depend>
<exec_depend>rosidl_default_runtime</exec_depend>
<member_of_group>rosidl_interface_packages</member_of_group>
```

### 6. 构建 & 查看

```bash
cd /home/u24/MyTest/dev01/ros2/test_ws01
colcon build --packages-select arm_demo_msgs
source install/setup.bash

ros2 interface show arm_demo_msgs/msg/ServosPosition
ros2 interface list | grep arm_demo
```
预期：打印出字段定义。

### 7. 在节点里用

```python
from arm_demo_msgs.msg import ServosPosition, ServoPosition
from arm_demo_msgs.srv import GetState

msg = ServosPosition()
msg.duration = 0.5
sp = ServoPosition()
sp.id = 6
sp.position = 600
msg.position.append(sp)
```

---

## 原理（极简）

- msg/srv 是**接口定义（IDL）**；构建时自动生成 C++/Python 类。
- `pkg/Type[]` 表示数组；`---` 分隔 srv 请求/应答。
- 生成物在 `install/<pkg>/lib/python3.12/site-packages/<pkg>/`。

## 常见坑

- 消息包**必须先 build**，用它的包才 build 得过。
- 改了 `.msg` → 用到它的包都要重新 build。
- 类型要写对（`uint16` vs `float64`），否则数值会截断。
