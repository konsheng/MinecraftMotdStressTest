# MinecraftMotdStressTest 压测工具（Python 版）

本项目提供一个完整、易用的 Python 脚本，用于对 Minecraft Java 服务器的 MOTD（Server List Ping）进行压力测试。它能够：

- **同步 Ping**：在压测前对服务器进行一次 `status` 请求，渲染并显示 MOTD 文本（保留 Minecraft 原始颜色代码），并展示在线/最大玩家数、服务端版本、Ping 延迟等信息。  
- **并发压测**：使用 `ThreadPoolExecutor` 并发发送大量 `status` 请求，模拟大量客户端同时查询 MOTD 的场景，测量延迟和成功率。  
- **限速功能**：支持全局 QPS 限制（Requests Per Second），避免瞬时打穿网络或触发服务器防护。  
- **超时 & 重试**：对每次请求可设置超时时间，并支持失败重试次数，提高统计的稳定性。  
- **彩色进度条**：在“提交任务”和“收集结果”两个阶段分别绘制动态进度条，并采用终端 ANSI 颜色展示，让用户一目了然地看到完成度。  
- **日志功能**：可选将详细运行日志（包括每次请求的延迟）写入文件，方便后期分析；控制台仅输出 WARNING 及以上级别信息，尽量保持简洁，不干扰进度显示。  
- **友好中断**：支持 **Ctrl+C** 随时中断测试，程序会统计当前已完成任务的结果并打印简明统计。

---

## 使用示例
![Honeycam 2025-06-06 02-19-14](https://github.com/user-attachments/assets/177b052c-b07d-484a-9ae5-bc991547fad0)

---

## 一、功能亮点

1. **MOTD 彩色渲染**  
   - 自动解析 Minecraft MOTD 中的 `§<代码>` 颜色/格式标识，将其转换为对应的 ANSI 颜色代码，直接在终端中以彩色效果显示。例如 `§a绿色文字` 能显示为绿色、`§l粗体文字` 显示为加粗等。

2. **分阶段进度条**  
   - **提交阶段**：将所有 `total` 次请求以指定的并发和限速方式提交到线程池，实时绘制“提交中”进度条，显示已提交任务数及百分比。  
   - **收集阶段**：在 `as_completed` 循环中实时收集每个请求结果，绘制“收集中”进度条，显示已完成任务数及百分比。  
   - 进度条采用绿色 `█` 符号，可直观反映当前进度。

3. **超时 & 重试机制**  
   - 每次 `server.status()` 调用都会带上 `--timeout` 值（例如 5 秒）。若请求超过超时则抛出异常。  
   - 可以通过 `--retries` 设置失败重试次数，默认 0（不重试）；如果网络抖动、偶发超时，自动重试可减少统计误差。

4. **QPS 限速**  
   - 如果指定了 `--qps`（每秒最大请求数），脚本会在每次提交任务前执行 `time.sleep(1.0 / qps)`，控制全局请求速率，避免一股脑儿打满带宽或触发 DDOS 防护。

5. **日志记录**  
   - 可选参数 `--logfile` 指定一个日志文件路径。  
   - 成功请求的延迟信息、失败原因等都会以 `INFO` 级别写入日志文件。  
   - 控制台仅输出 `WARNING` 及以上级别日志，例如重试提示、最终统计、严重错误，不会被大量 “请求成功” 日志刷屏。

6. **完整统计指标**  
   - **总请求数**、**成功数**、**失败数**、**成功率**  
   - **平均延迟**（单位：毫秒）、**最小延迟**、**最大延迟**、**P99 延迟**  
   - **每秒请求数分布**（REQ/s）：统计每一秒实际发起的请求次数，帮助评估限速是否达到预期。

7. **中断保护**  
   - 在压测过程中按下 **Ctrl+C**，程序会停止提交新任务，并统计当前已完成任务的结果（包括成功与失败），然后打印中断时的统计信息，最后优雅退出。

---

## 二、环境依赖

- **Python 版本**  
  - 推荐使用 Python 3.7 及以上。

- **第三方库**  
  ```bash
  pip install mcstatus colorama
  ```
  - `mcstatus`：用于与 Minecraft 服务器交互，执行 `status()` 请求。  
  - `colorama`：在 Windows/macOS/Linux 终端中渲染 ANSI 颜色。

---

## 三、脚本文件结构

本项目仅包含一个核心脚本 `motd_stress_test_optimized.py`。其主要逻辑分为以下几个部分：

1. **颜色映射与 MOTD 解析** (`parse_motd`)  
   - 定义 `MC_ANSI_MAP`，将 Minecraft `§` 颜色/格式码映射到 `colorama` 对应的 ANSI 码。  
   - 函数 `parse_motd(motd: str) -> str`：使用正则替换方式，将 MOTD 中所有 `§<code>` 替换为对应的 ANSI 码，并在末尾添加 `Style.RESET_ALL`，避免后续文字被“染”色。

2. **彩色帮助信息** (`print_colored_help`)  
   - 手动打印一段带多种颜色的帮助文本，包括：用法示例、参数说明、功能流程、注意事项等。  
   - 如果用户在命令行传入 `-help` 或 `--help`，则调用此函数并退出。

3. **日志配置** (`setup_logging`)  
   - 创建 `logging.Logger`，设置日志级别为 `INFO`。  
   - 控制台 `StreamHandler`：级别 `WARNING`，只输出警告和错误，确保进度条不会被大量日志打断。  
   - 可选文件 `FileHandler`：如果传入了 `--logfile <路径>`，则将 `INFO`（包含每次请求延迟）及以上日志写入该文件，方便后续查看。

4. **Ping 阶段** (`ping_server`)  
   - 调用 `server.status(timeout=…)`，获取原始 MOTD、在线玩家数、最大玩家数、服务端版本、延迟等信息。  
   - 如果 `mcstatus` 版本不支持 `timeout` 参数，则退回到无超时调用（不推荐）。  
   - 渲染 MOTD 颜色后在终端打印：  
     ```
     ====== 服务器基本信息 ======
     MOTD             : <彩色 MOTD>
     在线玩家数       : <当前>/<最大>
     服务端版本       : <版本>
     单次 ping 延迟   : <XX.XX> ms
     ============================
     ```

5. **压测阶段**  
   1. **参数校验**  
      - 必填：`--host`、`--total`；  
      - `--concurrency`、`--total` 必须为正整数；  
      - `--qps`、`--retries` 必须为非负整数；  
      - `--timeout` 必须为正数。  
      - 校验失败时以红色文字提示并退出。

   2. **ThreadPoolExecutor 提交任务**  
      - 计算 `delay_per_req = 1.0 / qps`（若 `qps > 0`），否则为 0。  
      - 用一个循环提交 `total` 次 `executor.submit(query_motd_sync, server, timeout, retries, logger)`：  
        - 每次提交前，如果 `delay_per_req > 0`，则 `time.sleep(delay_per_req)`。  
        - 记录当前系统秒数 `sec = int(time.time())`，并累加 `req_per_second[sec] += 1`。  
        - 每提交一轮后调用 `draw_progress("提交中", submitted, total)` 更新“提交中”进度条。  
        - 每 500 次提交时，在新行打印一次简要进度：  
          ```
          [HH:MM:SS] 已提交 XXX/总 共YYYY 次请求，用时 ZZ.ZZ 秒
          ```

   3. **收集结果并统计**  
      - 提交完成后，调用 `draw_progress("提交中", total, total)` 确保进度条满格。  
      - 开始 `completed = 0`，调用 `draw_progress("收集中", completed, total)`。  
      - 在 `for fut in as_completed(futures)` 循环中：  
        - `fut.result()`：  
          - 如果成功返回延迟 `elapsed_ms`，则将其写入 `stats["latencies"]` 并将 `stats["success"] += 1`，成功日志只写到文件。  
          - 如果抛异常（超时/连接失败/重试后仍失败），在控制台换行打印红色错误 `"[错误] HH:MM:SS 查询失败：<异常信息>"`，并重画进度条，再在日志文件写一行 `ERROR` 级别日志。此时 `stats["failure"] += 1`。  
        - 之后 `completed += 1`，并调用 `draw_progress("收集中", completed, total)` 更新“收集中”进度条。

6. **中断处理**  
   - 在提交或收集阶段，用户按 **Ctrl+C** 会触发 `KeyboardInterrupt`。  
   - 脚本会先打印红色提示：  
     ```
     检测到 Ctrl+C 中断，停止提交新任务并只汇总已完成任务结果...
     ```  
   - 稍作 `time.sleep(0.1)`，让少数正在执行的任务有机会结束。  
   - 遍历 `futures` 列表，仅对 `fut.done()` 为 `True` 的任务再次调用 `fut.result()`（若失败则计为失败、若成功则计为成功）。累加得到 `done_count`。  
   - 分别调用 `draw_progress("提交中", submitted_or_total, total)` 和 `draw_progress("收集中", done_count, total)`，显示中断时的进度状态。  
   - 最后调用 `print_stats(stats, done_count)`，打印当前已完成任务的统计信息，并以 `sys.exit(0)` 退出。

7. **最终统计**  
   - `draw_progress("提交中", total, total)` 和 `draw_progress("收集中", total, total)`，确保进度条满格。  
   - 调用 `print_stats(stats, total_requests)`，输出：  
     ```
     ======= 当前统计结果 =======
     已完成请求数   : XX
     成功请求数     : YY
     失败请求数     : ZZ
     成功率         : Aa.BB%
     平均延迟(ms)   : XX.XX
     最小延迟(ms)   : YY.YY
     最大延迟(ms)   : ZZ.ZZ
     P99 延迟(ms)   : PP.PP

     ====== 每秒请求数 (REQ/s) ======
     2025-06-05 23:50:00 → 200
     2025-06-05 23:50:01 → 200
     ……
     ```  
   - 同时将 “压测结束，打印统计结果” 以 `INFO` 级别写入日志文件。

---

## 四、快速上手

1. **克隆或下载脚本**  
   ```bash
   git clone <本项目仓库地址>
   cd <项目目录>
   ```

2. **创建并激活虚拟环境（可选）**  
   ```bash
   python3 -m venv venv
   source venv/bin/activate   # macOS/Linux
   venv\Scriptsctivate      # Windows PowerShell
   ```

3. **安装依赖**  
   ```bash
   pip install mcstatus colorama
   ```

4. **查看帮助（彩色显示）**  
   ```bash
   python motd_stress_test_optimized.py -help
   ```  
   你会看到如下内容：  
   ```
   ======================== 帮助信息 ========================
   用法示例:
     python motd_stress_test_optimized.py --host 119.188.247.168 --port 20000 --concurrency 100 --total 5000 --qps 200 --timeout 5 --retries 1 --logfile test.log

   参数说明:
     --host, -H           目标服务器地址或 IP（必填）。
     --port, -P           目标服务器端口，默认 25565。
     --concurrency, -c    并发线程数（最大同时查询数量），默认 50，须为正整数。
     --total, -n          总请求次数（必填），须为正整数。
     --qps, -q            全局限速（每秒最大请求数），默认 0（不限制），须为非负整数。
     --timeout, -t        单次查询超时（秒），默认 5.0 秒，须为正数。
     --retries, -r        失败重试次数，默认 0 次，须为非负整数。
     --logfile, -l        可选：指定日志文件路径，将 INFO 及以上日志写入文件；控制台只显示 WARNING+。

   功能说明:
   - 首先对目标服务器进行一次同步 ping，渲染并打印 MOTD：
       带颜色的 MOTD 文本、在线/最大玩家数、服务端版本、Ping 延迟(ms)
   - 然后使用多线程并发方式按给定参数进行 MOTD 查询压力测试。
   - 压测分两个阶段显示进度：
       1. 提交中：将所有请求 Task 提交到线程池，实时显示“提交进度条”。
       2. 收集中：调用 as_completed 逐一收集结果，实时显示“收集中进度条”。
   - 成功请求延迟只写入日志文件（若指定），不再输出到控制台；失败时会在控制台以红字提示。
   - 支持 Ctrl+C 随时中断，程序会统计并展示已完成的请求结果。

   具体流程:
   1. 检查并解析参数，进行基本校验。
   2. 使用 mcstatus 对服务器执行一次 status（带 timeout），并调用 parse_motd 渲染 MOTD。
   3. 显示服务器基本信息（彩色输出）。
   4. 进入压测：创建 ThreadPoolExecutor 并发提交任务，
      每个任务调用 mcstatus.status() 获取 MOTD，超时/失败可重试 --retries 次。
   5. 在“提交中”阶段绘制绿色“█”进度条，实时反映已提交任务数。
   6. 在“收集中”阶段同样绘制进度条，收集完成数并统计：
      - 成功：延迟数据保存在 stats，日志写入文件（INFO）。
      - 失败：在控制台输出红色提示（ERROR），同时写日志文件。
   7. 全部完成或中断后，打印统计结果，包括：
      - 总请求数、成功数、失败数、成功率
      - 平均延迟、最小延迟、最大延迟、P99 延迟
      - 每秒请求数分布（REQ/s）

   注意事项:
   - 确保对目标服务器已获得管理员授权，避免被误判为恶意流量。
   - 如果并发数和 QPS 设置太高，可能触发防火墙或 DDOS 防护机制。
   - 建议在服务器低峰期进行测试，并监控服务器端 TPS、CPU、内存、网络带宽。
   - 若需可视化分析，查看日志文件中的延迟数据，或后续绘图。
   ==========================================================
   ```

5. **执行压测示例**  
   - **简单示例（不写日志）**  
     ```bash
     python motd_stress_test_optimized.py --host play.example.com --total 1000
     ```  
     - 使用默认并发 50、QPS 不限制、超时 5 秒、不重试、不写日志。  
     - 脚本会 ping 一次 `play.example.com`：渲染并显示 MOTD 及服务器信息。  
     - 随后以 50 并发同时发起 1000 次 `status()` 请求，实时打印“提交中”和“收集中”进度条。  
     - 所有请求完成后，打印详细统计并退出。

   - **启用所有功能示例（带日志、限速、重试）**  
     ```bash
     python motd_stress_test_optimized.py --host play.example.com --port 25565 --concurrency 200 --total 5000 --qps 100 --timeout 3 --retries 2 --logfile motd_test.log
     ```  
     - 并发 200，QPS 限制 100，请求超时 3 秒，每次请求失败可重试 2 次。  
     - 所有成功请求的延迟信息写入 `motd_test.log`，控制台只显示失败和警告信息。  
     - 执行期间可以按 **Ctrl+C**，立刻停止新任务提交，统计并显示当前已完成任务结果，然后退出。

6. **日志示例（若指定了 `--logfile`）**  
   ```
   2025-06-06 10:00:00,123 [INFO] 启动压测：host=play.example.com, port=25565, concurrency=200, total=5000, qps=100, timeout=3.0, retries=2, logfile=motd_test.log
   2025-06-06 10:00:00,456 [INFO] 域名 play.example.com 已解析并使用 IP 进行连接。
   2025-06-06 10:00:00,789 [INFO] Ping 成功
   2025-06-06 10:00:05,123 [INFO] 请求成功，延迟：45.89 ms
   2025-06-06 10:00:05,125 [INFO] 请求成功，延迟：51.22 ms
   2025-06-06 10:00:05,126 [WARNING] 查询失败（第 1 次重试）：请求超时
   2025-06-06 10:00:05,130 [INFO] 请求成功，延迟：70.03 ms
   2025-06-06 10:00:06,000 [INFO] 所有请求提交完毕
   2025-06-06 10:00:07,500 [ERROR] 查询失败：请求超时
   2025-06-06 10:00:10,000 [INFO] 压测结束，打印统计结果
   ```

---

## 五、项目文件

```
motd_stress_test_optimized.py   # 核心脚本，包含所有功能模块
README.md                       # 本文件，详细项目介绍
```

> 如果想要模块化管理，可将各部分函数提取到 `utils.py`、`ping.py`、`stress.py` 等子模块，再在主脚本中导入。但本项目直接使用单文件分层结构即可快速部署和使用。

---

## 六、常见问题

1. **“Terminal does not support ANSI”**  
   - 如果你在老旧 Windows CMD 下无法看到颜色，请尝试在 PowerShell 或 Windows Terminal 中运行，或者安装 `ansicon` 等工具启用 ANSI 支持。

2. **为何“收集中”阶段看不到成功日志？**  
   - 设计初衷是保持进度条行不被“刷屏”打断；所有成功日志都写到 `--logfile`（`INFO` 级别），若需要查看每次延迟，请打开对应日志文件。

3. **如何查看失败次数及原因？**  
   - 失败的日志会以 `ERROR` 级别输出到控制台，并同时写入日志文件；你也可以在日志文件中搜索 `ERROR` 关键字查看每次失败原因和时间戳。

4. **长时间运行或内存占用**  
   - 如果 `--total` 非常大（如数万甚至数十万次请求），脚本会一次性创建等量的 `Future` 对象，可能占用大量内存。  
   - 若需更节省内存，请考虑修改为“分批提交”或使用 `asyncio` 异步版本，将并发请求数量限制在较小窗口（如 1000）内；后续版本可进一步优化。

5. **为何使用 `ThreadPoolExecutor` 而不是纯 `asyncio`？**  
   - 使用线程池能兼容各版本 `mcstatus`。如果你熟悉异步编程，也可以改写为 `asyncio` + `status_async()`，进一步减少线程上下文切换开销。

---

## 七、后续可扩展方向

- **批量/多服务器压测**：支持从 CSV/JSON 中读取服务器列表，一键批量压测并汇总报告。  
- **可视化报表**：自动生成延迟直方图、时序图、成功率曲线等，并导出为 HTML 或 PPT。  
- **Prometheus/InfluxDB 接入**：实时推送指标到监控系统，可在 Grafana 中动态查看。  
- **定时调度 & 通知**：定期压测并发送邮件/钉钉/Slack 通知，结合监控告警流转。

---

## 八、许可证

本项目采用 MIT License，欢迎自由使用、修改和分发。详细见：[LICENSE](LICENSE)。

---

**感谢使用！**  
如有疑问或建议，欢迎提交 Issue 或 Pull Request。  

> **作者**：Konsheng
> **日期**：2025-06-06
> **版本**：v1.0.0
