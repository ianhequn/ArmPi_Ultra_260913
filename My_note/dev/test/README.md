# 测试脚本（手动工具）

> 索引：[`../pi_project_mem.md`](../pi_project_mem.md)（项目枢纽）

## 前提

- 机械臂主控板已接入：`/dev/ttyUSB0`（CH340），波特率 `1000000`
- 每次运行前先 source 环境：
  ```bash
  source /opt/ros/jazzy/setup.bash
  source /home/u24/MyTest/dev01/ros2/test_ws01/install/setup.bash
  ```

## 脚本

| 脚本 | 用途 | 是否需要节点 |
| --- | --- | --- |
| `read_servo_id.py` | 直连 SDK，读 6 个舵机 ID | 否 |
| `read_servo_state.py` | 直连 SDK，读位置/电压/温度 | 否 |
| `test_service.py` | 启动驱动节点 + 调 `get_state` 服务，读舵机 ID | 自启 |
| `demo_move.py` | 启动驱动节点 + 经话题小幅摆动舵机 5 并复位 | 自启 |

## 运行

```bash
python3 My_note/dev/test/read_servo_id.py
python3 My_note/dev/test/demo_move.py
```

> 注意：直连 SDK 的脚本与驱动节点**不能同时**占用串口。
> CH340 在进程刚退出后短暂报 `Input/output error`，等 1~2 秒再开即可。
