# VM 侧问题汇总 —— SmolVLA 六轴机械臂控制 POC

> 用途：**简历素材 / 复盘**。
> 项目：ROS2 (Jazzy) 六轴机械臂控制 POC —— 移植幻尔(Hiwonder) STM32 机械臂控制栈，
> 打通「宿主机(Windows, 无 ROS2) ↔ VM ↔ 舵机总线」的**数据采集 + 回放/推理**闭环。
> 技术栈：ROS2 Jazzy / rclpy / colcon / 串口协议(STM32 自定义帧) / TCP-JSON / LeRobot·SmolVLA 数据链路。

---

## 0. 项目构成（对照简历：7 包 · 5 节点）

| 包 | 节点 | 职责 |
|---|---|---|
| `ros_robot_controller_msgs` | — | 驱动层接口定义（`ServosPosition` / `GetBusServoState` / `SetBusServoState` …） |
| `ros_robot_controller` | `ros_robot_controller` | **驱动层**：CH340 串口 ↔ `AA 55 + func + len + data + CRC8` 帧，舵机读写/扭矩 |
| `servo_controller_msgs` | — | 语义层接口定义 |
| `servo_controller` | `servo_controller` | **语义网关**：关节名 ↔ 舵机 id，`rad`/`deg`/`pulse` 换算，软限限幅、`flipped` 反向 |
| `arm_serial_bridge` | `serial_bridge` | 宿主机经**虚拟串口 ASCII 命令**控制（`PING/Q/H/A/L/E/R`） |
| `arm_vofaUDP_bridge` | `vofa_udp_bridge` | 上位机 **VOFA+ UDP(RawData ASCII)** 双向控制，JSON 配置 IP/端口 |
| `arm_lerobot_dataset_stream` | `dataset_stream` | **LeRobot 数据链路**：上行实测角 TCP-JSON 流 + 下行回放（复用一条连接） |

**5 个可运行节点**：`ros_robot_controller`、`servo_controller`、`serial_bridge`、`vofa_udp_bridge`、`dataset_stream`。

---

## 1. 移植期：厂商代码 / 硬件层

| # | 问题 | 根因 | 解决 |
|---|---|---|---|
| 1.1 | **卸力(`L`)完全无效** | 厂商 SDK `bus_servo_enable_torque` 的 **`0x0B`/`0x0C` 写反**（实测 `0x0B`=关扭矩、`0x0C`=开扭矩） | 对调；读回验证 `[0]`=卸力 / `[1]`=保持 |
| 1.2 | 读扭矩状态报错 | `get_torque_state` 调了**不存在**的 `bus_servo_read_torque`（应为 `bus_servo_read_torque_state`） | 改调用名 |
| 1.3 | 串口抖动即**崩节点** | `recv_task`/`buf_write` 未捕获 `SerialException` → 线程死/节点退出 | 加异常容错 + **自动重连**（`_reopen`，加锁、重连前置 `rts/dtr=False`、失败计数） |
| 1.4 | IK / 笛卡尔无法移植 | 厂商 `kinematics` 的 `.so` 是 **aarch64**，x86_64 VM 不可用 | 明确**排除笛卡尔**，只做关节/脉宽控制（写进设计边界） |
| 1.5 | 厂商源码跑不起来 | Python **3.10 → 3.12** 兼容 | 逐条修；厂商 Python 包**关闭 flake8/pep257 风格门禁**，业务代码零改动 |
| 1.6 | 两个同型号 CH340 **无法区分** | `1a86:7523` **无唯一序列号** → `/dev/serial/by-id/` 名字冲突 | 改用 **`/dev/serial/by-path/`**（绑物理 USB 口）；识别法=逐口跑 `get_state` 看有无舵机响应 |
| 1.7 | 串口 `[Errno 5] Input/output error`，必须拔插 | CH340 在 **VMware USB 透传**下反复 open/close 会整体掉线 | ① 温柔退出（禁 SIGKILL）② **驱动打开串口自动重试 30×1s** → 实测 3s 内自愈，不用拔插③ 仍不行才拔插/VMware 重连 |

## 2. ROS2 工程化

| # | 问题 | 根因 | 解决 |
|---|---|---|---|
| 2.1 | 节点启动即**崩溃** | 自定义成员 `self._clients` **与 rclpy `Node` 内部属性重名** | 改名 `_tcp_clients`/`_tcp_lock` |
| 2.2 | 启动时卸力**不生效**（静默丢包） | 时序竞争：`dataset_stream` 在驱动就绪前就发扭矩关 → 消息丢失 | 等驱动 **`init_finish`(Trigger) 服务**就绪后再发（并连发两次防丢帧） |
| 2.3 | 软限与硬限不一致（撞限位/异响） | yaml 软限是拍的，未对齐舵机内部硬限 | 直连 SDk 读 **`0x32` 硬限**（id1=[0,700]、id5=[125,875]）+ 手推探测机械范围 → **软硬限一致**；`joint4` 例外收紧 −100°~+90° |
| 2.4 | `/joint_controller` 使能后异常 | 厂商回调实现有 bug | 标注**勿用**，统一走 `/servo_controller`（`ServosPosition`） |
| 2.5 | 厂商包 `colcon test` 报风格错 | ament 默认 flake8/pep257 门禁 | 移植的厂商代码关闭门禁，自研包保持**全绿** |

## 3. 实时性与协议设计

| # | 问题 | 根因 | 解决 |
|---|---|---|---|
| 3.1 | **慢客户端拖垮整条采样** | TCP **发送端无"丢弃"语义**：`sendall` 后字节进内核 `SO_SNDBUF`，只能排队；客户端不读 → 采样率从 20Hz 掉到 10.7Hz 且被误踢 | 上/下行都改为**覆盖式单槽变量 + 每客户端独立发送线程**：生产端只覆盖写变量不碰 socket，发送完再取最新、**跳过即丢**（`SO_SNDBUF=2048` 有界 + `_dropped` 计数）→ 实测客户端 4 秒不读，采样仍稳 20Hz |
| 3.2 | 采样率上不去 / 总线顶满 | 实测串口读耗时：**1 舵机 6.4ms(155Hz)、6 舵机 35ms(~28Hz)** | 定出**硬上限**，`poll_rate_hz` 建议 20~25（默认 30 会顶满总线，挤压下发窗口） |
| 3.3 | VOFA+ 命令**粘连**（`5.9A` 被当成一个数） | RawData ASCII **不带行分隔符**，多条命令连在一起 | 写 `protocol.split_commands()`：在命令关键字处切分 + 数字后紧贴的字母拆开（`5.9A`→`5.9 A`，`T800`→`T 800`），串口桥/UDP 桥共用 |
| 3.4 | 慢客户端被**误踢**且 JSON 行被**撕坏** | reader 线程对**同一 socket** 调 `conn.settimeout(0.5)` → 该 socket 的 `sendall` 被改成超时模式，部分写入 | reader 改用 **`select.select`** 等待可读，不再改 socket 超时；并加 `TCP_USER_TIMEOUT` |

## 4. 疑难杂症（简历最有价值的部分）

### 4.1 回放中途"卡死"：`no measured frames` 单调增长

**现象**：`no measured frames for 2.0s → 7.0s → 12.1s`（**只增不减、永不恢复**），
同时 `downlink: 22.7 Hz state=ARMED` 一直正常；驱动日志停在 `bus_servo_read_position: [223]`（6 个舵机只读了 4 个）后**再无输出**。

**排查路径（逐步推翻假设）**：

1. 排除**看门狗**（命令率 22.6Hz，无 timeout）、排除**录制数据完整**；
2. 硬件实测**下发链路通**（下发 joint1 +0.10 rad → 实测跟到 +0.093 rad）；
3. 一度误判为「**斜坡限速追不上录制动作**」（日志有 `ramp lagging joint2: target 0.092 but sending 0.562`，差 54°）→ 于是删掉限速；
4. **真根因**（读代码定位）：厂商 SDK
   ```python
   with self.servo_read_lock:
       self.buf_write(...)
       data = self.bus_servo_queue.get(block=True)   # ← 无超时，且持有锁
   ```
   任何一次读响应丢失 → **永久阻塞** → 锁再也放不掉 → 之后**所有**读（同一轮里剩下的舵机、所有后续 `get_state`）全部死等 → 状态服务**永久瘫痪**。所以是"死了"不是"慢"。

5. **触发条件的定位（关键实验设计）**：
   先做**阶梯负载实验**——把当前角度按 **20 / 40 / 77 Hz** 回写（手臂**原地不动**），同时 25Hz 轮询读 →
   **0 次读超时**。**证伪"总线负载"假设**；
   再看失败 run 时间轴：`纯读 3.7 秒完全正常 → armed 后手臂一开动 → 1.2 秒内就死` →
   锁定**手臂真实运动时的电流尖峰** 导致串口丢一次响应。

**修复**（4 处，全部围绕"永不死锁"）：

| 修复 | 内容 |
|---|---|
| 读加超时 | `bus_servo_read_and_unpack(timeout=0.3)`，超时返回 `None`（所有调用方本就判 `if state is not None`，天然兼容） |
| 清残留 | 发请求**前** `get_nowait()` 清空回包队列（清掉上次超时/写命令的残留） |
| 回包校验 | 回包按 **`id`/`cmd` 匹配**，不匹配就丢弃继续等（避免错位一格导致位置变垃圾） |
| 线程保命 | `recv_task` 解析段整体 `try/except`（**接收线程死 = 永久卡死**，绝不允许） |

**实测证据**：

| 测试 | 修前 | 修后 |
|---|---|---|
| 读不存在的 id99（= 模拟丢响应） | 永久阻塞 | **0.10s 返回 `None`** |
| 卡过之后再读正常舵机 | 永久读不到 | **0.01s 返回 497** |
| **20Hz 写 + 30Hz 读 连续 20 秒** | （必卡） | **0 读超时、0 卡流** |
| 重放原失败数据集 | 卡住 | ✅ **回放成功** |

**并诚实修正了自己引入的 regression**：为治"请求叠加"加的 `_pending` 守卫（上一条没回来就不发新的），反而把**可恢复的降级变成硬永久卡死** → 加 **3s 兜底**（超时太久就丢弃重发）。

### 4.2 接收线程被 `TypeError` 悄悄杀死

`_reopen()` 关端口时把 `self.fd` 置 `None`，而 `recv_task` 正阻塞在 `read()` 里 → `os.read(None, ...)` 抛 `TypeError`；原代码只 `except (SerialException, OSError)` → **线程死掉**，于是"串口还在收、但再没人解析" → 所有 `get_state` 永久阻塞。**修复**：加宽异常捕获，让接收线程活着。

### 4.3 诊断环境本身的坑

| 现象 | 根因 | 处理 |
|---|---|---|
| 新实例启动即 `OSError: [Errno 98] Address already in use` | 上次 `Ctrl+C` 留下的**残留进程仍占着 1348**（`SO_REUSEADDR` 挡不住活跃 LISTEN） | 裸 traceback → 改为**给人话的报错**（提示 `ss -ltnp \| grep 1348`）；并签入 `cleanup_arm_stack.sh` |
| 清理命令**把自己杀掉** | `pkill -f dataset_stream` 会匹配到**发起命令的 shell 自身 cmdline** | 清理脚本改用 `ps + awk` 规避 |
| 串口报 `multiple access on port` | 5 个 `ros_robot_controller` 抢 `/dev/ttyUSB0` | 单实例约束 + 清理脚本 |

## 5. 沉淀的方法论（简历可写的"能力点"）

1. **分级隔离**：硬件 → 串口 → 驱动 → 网关 → 语义 → 网络 → 应用，逐层加观测点定位。
2. **用实验证伪假设**：先排除"总线负载"（77Hz 写入 0 超时），才敢锁定"电流尖峰"。
3. **可观测性优先**：把沉默的失败变成明确告警（`driver NOT ready`、`cannot bind ... another dataset_stream is running`、`bus_servo read timeout`、`no measured frames for Ns: <原因>`）。
4. **消灭"永久阻塞"**：凡阻塞等待必须带超时 + 可恢复；凡出错必须让**关键线程不死**。
5. **组件化 / 最小改动**：厂商代码零业务改动（只修 bug）；自研部分按"纯逻辑可单测"拆分（如 `downlink.py` 无 ROS/socket 依赖，独立单测）。
6. **安全设计**：看门狗（静默/断连 → SAFE + 卸力）、录制默认 `enable_downlink=false`（零干扰）、上力连发两次。
7. **覆盖式数据面**：解耦"生产者频率"与"消费者频率"（丢帧优于阻塞）。

## 6. 可量化成果

- **7 个包 / 5 个节点**全部硬件验证，覆盖 3 条独立控制入口（ROS topic、虚拟串口 ASCII、UDP/VOFA+）。
- 上行实测角流：TCP + 换行 JSON，多客户端广播，**慢客户端不掉速**（4 秒不读仍稳 20Hz）。
- 下行回放：**22.7 Hz 命令率真机回放成功**（原失败数据集修复后通过）。
- 定位并修复**厂商 SDK 4 个 bug**（扭矩位反、函数名错、阻塞读无超时、异常未捕获死线程）+ 自研 regression 1 个。
- 软限与舵机硬限（`0x32`）**100% 对齐**（实测读出 6 个舵机硬限）。
- `colcon test` 全绿；下行集成测试（假驱动）**27 项断言全过**。

---

## 7. 简历可直接用的一行式写法（备选）

- 移植幻尔 STM32 六轴机械臂控制栈到 ROS2 Jazzy（**7 包 5 节点**），分层为「驱动 / 语义网关 / 应用」，打通宿主机（**不装 ROS2**）经 TCP-JSON 的实测角采集与动作回放闭环。
- 定位并修复厂商 SDK **无超时阻塞读 + 持锁**导致的机械臂状态服务**永久死锁**（曾表现为回放随机卡死）；通过**阶梯负载实验证伪总线负载假设**，锁定运动电流尖峰触发串口丢响应，修复后丢包仅造成 0.3s 抖动而非永久瘫痪。
- 设计**覆盖式（最新帧）数据面**解耦生产/消费频率：上行慢客户端不再拖垮采样（20Hz 稳定），宿主机可任意改 fps。
- 修复 `Node` 内部属性重名崩溃、启动时序竞争丢包、同型号 CH340 无法区分（改用 `by-path`）、VMware 下 CH340 掉线自愈等问题。
