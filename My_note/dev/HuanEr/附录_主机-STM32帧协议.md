# 附录 · 主机 ↔ STM32 帧协议

> 非 ROS2 层。上文各功能域的"帧"列都指向这里。
> 依据：`STM32/JetArmF4_Firmware/Hiwonder/Misc/packet.h`、`checksum.c`、`System/packet_handle.c`

---

## 1. 帧格式

```
AA 55 | func(1B) | len(1B) | data(len B) | crc8(1B)
```

| 项 | 说明 |
| --- | --- |
| 帧头 | `0xAA 0x55` |
| `func` | 功能码，见 §2 |
| `len` | **data 区**字节数（不含头/len/crc） |
| `crc8` | `crc8(func, len, data...)` —— **不含 `AA 55`**；查表法（`checksum.c`） |

**总长 = 5 + len**

### 请求/响应与主动上报

- 命令由主机下发；STM32 对**部分**命令回一条同 `func` 的包
- 舵机回包 data 布局：`servo_id | sub_command | success | args[8]`
- ⚠️ **`set_position`(0x01) 不回包**（实测：写 1 次 → 收到 0 个回包）
- ⚠️ STM32 还会**周期性地主动上报**（见 §4），会混在回包之间

### 实测样例（逐字节）

```
AA 55 00 03 04 82 1E 2A
│  │  │  │  └──┴─ data: 04 82 1E
│  │  │  └─────── len = 3
│  │  └────────── func = 0 (SYS)
│  └───────────── 帧头
└──────────────── CRC8 = 0x2A ✓

data = 04 | 82 1E → sub_cmd=0x04(电池) + uint16 LE 0x1E82 = 7810 → 7.810 V
```

---

## 2. func 码表（`class PacketFunction` / 固件 `enum PACKET_FUNCTION`）

| 值 | 名称 | 固件注册 | 方向 | 归属域 |
| --- | --- | --- | --- | --- |
| 0 | `SYS` | 上报 | STM32→主机 | [04 传感上报](04_传感上报.md) |
| 1 | `LED` | ✅ | 主机→STM32 | [02 声光](02_声光.md) |
| 2 | `BUZZER` | ✅ | 主机→STM32 | [02 声光](02_声光.md) |
| 3 | `MOTOR` | ✅ | 主机→STM32 | [03 电机](03_电机.md) |
| 4 | `PWM_SERVO` | ❌ | — | [06 死域](06_死域_固件未注册.md) |
| 5 | `BUS_SERVO` | ✅ | 双向 | [01 总线舵机](01_总线舵机.md) |
| 6 | `KEY` | 上报 | STM32→主机 | [04 传感上报](04_传感上报.md) |
| 7 | `IMU` | 上报 | STM32→主机 | [04 传感上报](04_传感上报.md) |
| 8 | `GAMEPAD` | 上报 | STM32→主机 | [04 传感上报](04_传感上报.md) |
| 9 | `SBUS` | 上报 | STM32→主机 | [04 传感上报](04_传感上报.md) |
| 10 | `OLED` | ❌ | — | [06 死域](06_死域_固件未注册.md) |
| 11 | `RGB` | ❌ | — | [06 死域](06_死域_固件未注册.md) |
| 12 | `CONVEYOR` | ❌ | — | [06 死域](06_死域_固件未注册.md) |
| 13 | `STEPPER_MOTOR` | ❌ | — | [06 死域](06_死域_固件未注册.md) |
| 14 | `NONE`（SDK 的边界） | — | — | 固件侧边界是 **10** |

> ⚠️ **SDK 比固件新**：SDK `NONE=14`（含 OLED/RGB/传送带/步进），本固件 `NONE=10` → 那些方法在本板无效。

---

## 3. 各 func 的 data 布局速查

| func | data 区 |
| --- | --- |
| `1` LED | `<BHHH` = `led_id, on_ms, off_ms, repeat`（**无子命令**） |
| `2` BUZZER | `<HHHH` = `freq, on_ms, off_ms, repeat`（**无子命令**） |
| `3` MOTOR | `sub` + 载荷；`0x01` 多路转速 / `0x05` 占空比 / `0x20` 直控 PWM |
| `5` BUS_SERVO | `sub` + 载荷；19 个子命令见 [01](01_总线舵机.md) §4 |

---

## 4. 周期上报结构体（`Portings/packet_reports.h`）

```c
PacketReportBatteryVoltageTypeDef { uint8_t sub_cmd; uint16_t voltage; }          // 实测 0x04
PacketReportKeyEventTypeDef       { uint8_t key_id; uint8_t event; }
PacketReportIMU_Raw_TypeDef       { float accel[3]; float gyro[3]; }
PacketReportIMU_Quat_TypeDef      { float w,x,y,z; }
PacketReportSerialServoTypeDef    { uint8_t servo_id; uint8_t sub_command;
                                    uint8_t success; uint8_t args[8]; }             // 舵机回包
PacketReportPWMServoTypeDef       { uint8_t servo_id; uint8_t sub_command; uint8_t args[8]; }
PacketReportGamepadTypeDef        { uint16_t buttons; uint8_t hat; int8_t lx,ly,rx,ry; }
PacketReportSBusTypeDef           { int16_t channels[16]; uint8_t ch17,ch18;
                                    uint8_t signal_loss; uint8_t fail_safe; }
```

**源码中的发送点**（全树 `packet_transmit` 搜索）

| 位置 | func | 触发 |
| --- | --- | --- |
| `System/app.c:28` | `KEY`(6) | 按键事件 |
| `Portings/imu_porting.c:44` | `IMU`(7) | IMU 采样 |
| `System/packet_handle.c` ×9 | `BUS_SERVO`(5) | 命令应答 |
| **（未找到）** | `SYS`(0) 电池 / `GAMEPAD`(8) / `SBUS`(9) | — ← 电池实测存在 |

---

## 5. 第二层：STM32 ↔ 总线舵机（舵机原生协议）

`Hiwonder/Peripherals/serial_servo.h`：帧头 `0x55`，命令码（LX 系列总线舵机标准）：

| 码 | 名称 | 码 | 名称 |
| --- | --- | --- | --- |
| 1 | MOVE_TIME_WRITE | 20 | ANGLE_LIMIT_WRITE |
| 2 | MOVE_TIME_READ | 21 | ANGLE_LIMIT_READ |
| 7 | MOVE_TIME_WAIT_WRITE | 22 | VIN_LIMIT_WRITE |
| 8 | MOVE_TIME_WAIT_READ | 23 | VIN_LIMIT_READ |
| 11 | MOVE_START | 24 | TEMP_MAX_LIMIT_WRITE |
| 12 | MOVE_STOP | 25 | TEMP_MAX_LIMIT_READ |
| 13 | ID_WRITE | 26 | TEMP_READ |
| 14 | ID_READ | 27 | VIN_READ |
| 17 | ANGLE_OFFSET_ADJUST | 28 | **POS_READ** |
| 18 | ANGLE_OFFSET_WRITE | 29 | OR_MOTOR_MODE_WRITE |
| 19 | ANGLE_OFFSET_READ | 30 | OR_MOTOR_MODE_READ |
| | | 31 / 32 | LOAD_OR_UNLOAD_WRITE / READ（扭矩） |
| | | 33 / 34 | LED_CTRL_WRITE / READ |
| | | 35 / 36 | LED_ERROR_WRITE / READ |

另：`CMD_SERVO_MOVE 0x03`（舵机内部批量执行命令）。

> **两层不要混**：主机侧读位置 `0x05` ≠ 舵机侧 `POS_READ=28`；
> 主机侧扭矩 `0x0B`/`0x0C` ≠ 舵机侧 `31`/`32`。
> STM32 负责翻译 —— **改主机侧子命令不需要懂舵机原生协议**。

---

## 6. 串口参数与性能

| 项 | 值 |
| --- | --- |
| 波特率 | `1000000`（驱动默认） |
| 格式 | 8N1，无流控 |
| 帧解析缓冲 | `PACKET_PARSE_BUFFER_SIZE = 64` |
| 读 1 个舵机 | **≈6 ms** |
| 读 6 个舵机（一轮） | **≈35 ms → ≈28 Hz 天花板** |
| 写 6 个舵机 | 实测 **77 Hz** 无错（6 倍余量） |

**接收端必须按帧解析 + 逐帧跳过**（会有主动上报混入），不能只匹配自己的回包。

---

## 7. 压测用现成报文（CRC 已验算）

| 用途 | 十六进制 |
| --- | --- |
| 写 1 个舵机 `id6→500, 40ms` | `AA 55 05 07 01 28 00 01 06 F4 01 5E` |
| 写 6 个舵机 `全500, 40ms` | `AA 55 05 16 01 28 00 06 01 F4 01 02 F4 01 03 F4 01 04 F4 01 05 F4 01 06 F4 01 62` |
| 读 id6 位置 | `AA 55 05 02 05 06 EC` |
| 卸力 id6 | `AA 55 05 02 0B 06 30` |
| 保持 id6 | `AA 55 05 02 0C 06 5E` |

**data 区构造规则**（设位置）：
```
01 | dur_lo dur_hi | n | (id, pos_lo, pos_hi) × n
```
`duration` 单位 **ms**；`pos` 0~1000；全小端。
