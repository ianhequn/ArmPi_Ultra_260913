# ROS2 机械臂项目：一步一步开发教程

> 目标：照着做能**跑通**本项目（幻尔机械臂控制 + 串口/UDP 桥 + LeRobot 数据流）。
> 只讲本项目实际用到的，不泛讲 ROS2。语言尽量简短。每步都有**命令 + 预期结果**。

---

## 学习路径

| 章 | 目标 | 对应代码 |
| --- | --- | --- |
| [00 环境与工作区](00_环境与工作区.md) | 知道怎么 source、怎么构建 | — |
| [01 官方建包与构建](01_官方建包与构建.md) | 用 `ros2 pkg create` 建包并跑起来 | 所有包 |
| [02 接口包 msgs](02_接口包msgs.md) | 写/生成 msg、srv | `*_msgs` |
| [03 驱动层：串口与协议](03_驱动层_串口与协议.md) | 打开串口、发 `AA55+CRC8` 帧 | `ros_robot_controller` |
| [04 语义网关](04_语义网关_servo_controller.md) | 单位换算 + 限位 + 话题契约 | `servo_controller` |
| [05 第一个动作](05_第一个动作.md) | 发一条话题让舵机动 | 端到端最小例 |
| [06 宿主串口桥](06_宿主串口桥.md) | 文本命令解析、粘连切分 | `arm_serial_bridge` |
| [07 UDP 桥（VOFA）](07_UDP桥_VOFA.md) | UDP + JSON 配置 | `arm_vofaUDP_bridge` |
| [08 LeRobot 数据流](08_LeRobot数据流.md) | TCP+JSON 流、轮询、线程 | `arm_lerobot_dataset_stream` |
| [09 调试与排错](09_调试与排错.md) | topic/service 排查、EIO | 全项目 |
| [10 常用命令与技巧](10_常用命令与技巧.md) | 命令速查、git/文档习惯 | — |

---

## 每章格式

```
> 目标：一句话
> 对应代码：src/xxx

## 步骤
命令 → 预期结果

## 原理（极简）
- 2~4 条

## 常见坑
- ...
```

## 约定

- 工作区：`/home/u24/MyTest/dev01/ros2/test_ws01`
- 每开一个新终端，先：
  ```bash
  source /opt/ros/jazzy/setup.bash
  source install/setup.bash
  ```
- 硬件：幻尔 STM32 板（CH340），`/dev/ttyUSB0`，波特率 `1000000`。

> 回链：[`../pi_project_mem.md`](../pi_project_mem.md)（项目枢纽）
