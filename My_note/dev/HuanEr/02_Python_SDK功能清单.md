# 02 · Python SDK 功能清单

> 文件：`ros_robot_controller/ros_robot_controller_sdk.py`（**910 行 / 42 个公开方法**）
> 位置：`enum PacketFunction` → `class Board`（协议层，收发都在这里）
> 「生效」列：`☑` = 本版固件已注册该 func；`✗` = 固件未注册，**调用无效**

---

## 1. 框架层（收发基础设施）

| 方法 | 参数 | 说明 |
| --- | --- | --- |
| `enable_reception(enable=True)` | | **直连读数据前必须先开**（默认 `False`，`recv_task` 只在开启时才读串口） |
| `recv_task()` | — | 接收线程：`AA 55` 状态机 → CRC 校验 → 按 func 分发到 6 个队列 |
| `buf_write(func, data)` | | 打包并发送一帧；含串口异常容错 + 自动重连（本工作区新增） |
| `Board.__init__(device, baudrate, timeout)` | | 打开串口；本工作区新增 **失败自动重试 30×1s** |

**内部队列**（`maxsize=1`，满则 `put_nowait` 静默丢弃）：

| 队列 | 收了什么 |
| --- | --- |
| `sys_queue` | SYS 包（电池电压等） |
| `bus_servo_queue` | **总线舵机回包**（读和写的回包都进这里 ⚠️） |
| `pwm_servo_queue` / `key_queue` / `imu_queue` / `gamepad_queue` / `sbus_queue` / `stepper_queue` | 各自上报 |

---

## 2. 总线舵机（19 个方法，本项目核心）

### 2.1 写

| 方法 | 参数 | sub | 生效 | 备注 |
| --- | --- | --- | --- | --- |
| `bus_servo_set_position` | `duration`(秒), `positions`=[[id,pos0~1000],…] | `0x01` | ☑ | **主力接口**；`duration*1000`→ms。**不回包** |
| `bus_servo_stop` | `servo_ids` | `0x03` | ☑ | 未实测 |
| `bus_servo_enable_torque` | `servo_id`, `enable` | `0x0B`/`0x0C` | ☑ | ⚠️ **厂商写反已对调**：`0x0B`=卸力，`0x0C`=保持 |
| `bus_servo_set_id` | `now`, `new` | `0x10` | ☑ | ⚠️ 写 Flash，**慎用** |
| `bus_servo_set_offset` | `servo_id`, `offset` | `0x20` | ☑ | 位置偏差 |
| `bus_servo_save_offset` | `servo_id` | `0x24` | ☑ | ⚠️ 写 Flash |
| `bus_servo_set_angle_limit` | `servo_id`, `[lo,hi]` | `0x30` | ☑ | ⚠️ 写硬限，**本项目不写** |
| `bus_servo_set_vin_limit` | `servo_id`, `[lo,hi]` | `0x34` | ☑ | ⚠️ 写 Flash |
| `bus_servo_set_temp_limit` | `servo_id`, `hi` | `0x38` | ☑ | ⚠️ 写 Flash |

### 2.2 读（统一入口 `bus_servo_read_and_unpack(servo_id, cmd, unpack, timeout)`）

| 方法 | sub | 返回 | struct | 实测 |
| --- | --- | --- | --- | --- |
| `bus_servo_read_position` | `0x05` | 位置 0~1000 | `<BBbh` | ✅ |
| `bus_servo_read_id` | `0x12` | id | `<BBbB` | ✅ |
| `bus_servo_read_offset` | `0x22` | 偏差 | `<BBbb` | — |
| `bus_servo_read_vin` | `0x07` | 电压 mV | `<BBbH` | — |
| `bus_servo_read_temp` | `0x09` | 温度 | `<BBbB` | — |
| `bus_servo_read_torque_state` | `0x0D` | 0=卸力/1=保持 | `<BBbb` | ✅ |
| `bus_servo_read_angle_limit` | `0x32` | `[lo,hi]` | `<BBb2H` | ✅ 读出 6 舵机硬限 |
| `bus_servo_read_vin_limit` | `0x36` | `[lo,hi]` | `<BBb2H` | — |
| `bus_servo_read_temp_limit` | `0x3A` | 上限 | `<BBbB` | — |

> 所有读方法内部都调 `bus_servo_read_and_unpack`，即 **读路径只有一条** —— 这是重构的抓手。

### 2.3 ⚠️ 已修复的硬缺陷（本工作区）

```python
# 原始厂商代码
data = self.bus_servo_queue.get(block=True)     # 无超时 + 持有 servo_read_lock
```
**后果**：读写共用 `PACKET_FUNC_BUS_SERVO`、队列 `maxsize=1`、读前不清残留 →
任何一次响应丢失/错位 → **永久阻塞且锁不再释放** → 整条读路径死（现象：`no measured frames` 单调增长）。

**修复**：`timeout=0.3s` 返回 `None` + 发请求前清空队列 + 按 `id/cmd` 匹配回包。

---

## 3. PWM 舵机（5 个方法，**固件未注册 → 无效**）

| 方法 | sub | 生效 | 备注 |
| --- | --- | --- | --- |
| `pwm_servo_set_position` | `0x01` | ✗ | 固件 `packet_pwm_servo_handle` 未注册 |
| `pwm_servo_set_offset` | `0x07` | ✗ | |
| `pwm_servo_read_position` | `0x05` | ✗ | |
| `pwm_servo_read_offset` | `0x09` | ✗ | |
| `pwm_servo_read_and_unpack` | — | ✗ | 统一读入口 |

> 固件里 PWM 舵机的子命令是 `0x01` 多个 / `0x03` 单个 / `0x05` 读位置 / `0x07` 设偏差 / `0x09` 读偏差。

---

## 4. 外设

| 方法 | func | 参数 | 生效 | 说明 |
| --- | --- | --- | --- | --- |
| `set_led` | LED(1) | `on_time`, `off_time`, `repeat`, `led_id` | ☑ | |
| `set_buzzer` | BUZZER(2) | `freq`, `on_time`, `off_time`, `repeat` | ☑ | |
| `set_motor_speed` | MOTOR(3) | `speeds`=[[id, 速度],…] | ☑ | 直流电机 |
| `set_motor_duty` | MOTOR(3) | `dutys` | ☑ | 占空比 |
| `set_motor_pwm` | MOTOR(3) | `speeds` | ☑ | |
| `set_oled_text` | OLED(?) | `line`, `text` | **✗** | SDK 比固件新 |
| `set_conveyor_speed` | CONVEYOR(?) | `speed` | **✗** | 同上（传送带） |
| `set_stepper_motor_position` | STEPPER(?) | `steps` | **✗** | 同上（步进电机） |
| `set_stepper_motor_subdivision` | STEPPER(?) | `subdivision` | **✗** | 同上 |

---

## 5. 上报类（从队列取，不主动发请求）

| 方法 | 返回 | 实测 |
| --- | --- | --- |
| `get_battery()` | 电压 (mV)，`data[0]==0x04` 才认 | ✅ 7.810 V |
| `get_button()` | 按键事件 | — |
| `get_imu()` | `<6f` 加速度+角速度 | — |
| `get_gamepad()` | `<HB4b` 手柄 | — |
| `get_sbus()` | SBus 通道 | — |

> ⚠️ 这些**不发请求**，只从队列取；拿不到就返回 `None`（对应 STM32 的周期上报，见 [01](01_主机-STM32协议.md) §4）。

---

## 6. 本工作区已硬件验证的方法（可放心用）

| 方法 | 佐证 |
| --- | --- |
| `bus_servo_set_position` | 位置/脉宽两种控制均实测 |
| `bus_servo_read_position` | 6 舵机读回正常，单次 ≈6ms |
| `bus_servo_enable_torque` | 卸力/保持实测（`0x0B`/`0x0C` 修正后） |
| `bus_servo_read_torque_state` | ✅ |
| `bus_servo_read_angle_limit` | 读出 id1=[0,700]、id5=[125,875]，其余 [0,1000] |

---

## 7. 重构建议（若动手）

| 优先 | 动作 |
| --- | --- |
| 1 | **抽出总线事务封装**：`bus_transaction(servo_id, sub, payload) -> (success, args)`，把"清队列→发包→按 id/cmd 匹配→超时"收敛到一处 |
| 2 | **删掉固件未注册的方法**（PWM/OLED/传送带/步进）或明确标注，减少误用 |
| 3 | **统一上报接口**：`get_*` 只取队列、不发请求，应改成"订阅式"（注册回调）或明确文档化 |
| 4 | 保留：帧编解码、CRC 表、解析状态机、19 个 `bus_servo_*` 的组合方式 |
| ❌ | 不要重写整个 SDK —— 真正的问题只有"读路径无超时"和"读写共用 func 队列"，都已有针对性修复 |
