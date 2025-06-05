#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
motd_stress_test_optimized.py

首先对目标 Minecraft 服务器进行一次同步 ping，渲染并显示 MOTD（Message of the Day）及在线/最大玩家数（带实际颜色输出）。
然后进入压力测试环节，使用 ThreadPoolExecutor + mcstatus 的同步接口，测量在不同并发和 QPS 条件下的响应延迟和成功率（带颜色输出）。
支持按 Ctrl+C 中断，并在中断时显示已完成的统计信息（带颜色输出）。
使用自定义绿色“█”进度条动态展示“提交任务”和“收集结果”两个阶段的进度。
优化点：
  - 增加 `--timeout` 和 `--retries` 参数，对每次 status 请求设置超时与重试机制。
  - 参数校验：`--host`、`--total` 必填，`--concurrency`、`--total`、`--qps` 必须为正整数。
  - 帮助信息完全汉化、丰富且带多种颜色，包含详细教程、示例和注意事项。
  - 可选 `--logfile`，将运行日志写入文件，便于事后分析。控制台仅显示 WARNING+ 级别。
  - “收集中”阶段只在失败时打印错误到控制台，成功只写入日志文件，不再干扰进度条输出。
  - 在 “ping” 阶段渲染 MOTD 中的 Minecraft 颜色代码（§代码）为终端 ANSI 颜色。
"""

import argparse
import time
import threading
import sys
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

from mcstatus import JavaServer  # 确保 mcstatus 版本支持 JavaServer.status(timeout)
from colorama import init, Fore, Style

# 初始化 colorama，让 Windows 终端也能显示颜色
init(autoreset=True)

# 线程安全的统计数据结构
stats_lock = threading.Lock()
stats = {
    "success": 0,
    "failure": 0,
    "latencies": []
}

# 用于记录每秒实际发起的请求数
req_per_second = defaultdict(int)

# 全局进度状态，用于重画进度条时不中断输出
progress_lock = threading.Lock()

# Minecraft § 颜色/格式化 代码 到 colorama ANSI 颜色/样式 的映射
MC_ANSI_MAP = {
    '0': Fore.BLACK,
    '1': Fore.BLUE,
    '2': Fore.GREEN,
    '3': Fore.CYAN,
    '4': Fore.RED,
    '5': Fore.MAGENTA,
    '6': Fore.YELLOW,
    '7': Fore.WHITE,
    '8': Fore.WHITE + Style.DIM,
    '9': Fore.BLUE + Style.BRIGHT,
    'a': Fore.GREEN + Style.BRIGHT,
    'b': Fore.CYAN + Style.BRIGHT,
    'c': Fore.RED + Style.BRIGHT,
    'd': Fore.MAGENTA + Style.BRIGHT,
    'e': Fore.YELLOW + Style.BRIGHT,
    'f': Fore.WHITE + Style.BRIGHT,

    'l': Style.BRIGHT,       # 粗体（Bright）
    'm': Style.DIM,          # 删除线（用 DIM 显示）
    'n': Style.NORMAL,       # 下划线（还原）
    'o': Style.NORMAL,       # 斜体（还原）
    'r': Style.RESET_ALL     # 重置
}

def parse_motd(motd: str) -> str:
    """
    将 Minecraft MOTD 中的“§<code>”格式替换为对应的 ANSI 颜色/样式码，
    返回一个可以直接 print 到终端的带 ANSI 控制码的字符串。
    """
    def repl(match):
        code_char = match.group(1).lower()
        return MC_ANSI_MAP.get(code_char, '')
    ansi = re.sub(r'§([0-9A-Frlomn])', repl, motd, flags=re.IGNORECASE)
    return ansi + Style.RESET_ALL


def print_colored_help():
    """
    手动输出彩色帮助信息，包括使用说明、参数详解、示例及注意事项。
    """
    print(Fore.CYAN + "======================== 帮助信息 ========================")
    print(Fore.YELLOW + "用法示例:")
    print(Fore.YELLOW + "  python motd_stress_test_optimized.py \\")
    print(Fore.YELLOW + "    --host 119.188.247.168 \\")
    print(Fore.YELLOW + "    --port 20000 \\")
    print(Fore.YELLOW + "    --concurrency 100 \\")
    print(Fore.YELLOW + "    --total 5000 \\")
    print(Fore.YELLOW + "    --qps 200 \\")
    print(Fore.YELLOW + "    --timeout 5 \\")
    print(Fore.YELLOW + "    --retries 1 \\")
    print(Fore.YELLOW + "    --logfile test.log")
    print()

    print(Fore.CYAN + "参数说明:")
    print(Fore.GREEN + "  --host, -H           " + Fore.WHITE + "目标服务器地址或 IP（必填）。")
    print(Fore.GREEN + "  --port, -P           " + Fore.WHITE + "目标服务器端口，默认 " + Fore.YELLOW + "25565" + Fore.WHITE + "。")
    print(Fore.GREEN + "  --concurrency, -c    " + Fore.WHITE + "并发线程数（最大同时查询数量），默认 " + Fore.YELLOW + "50" + Fore.WHITE + "，须为正整数。")
    print(Fore.GREEN + "  --total, -n          " + Fore.WHITE + "总请求次数（必填），须为正整数。")
    print(Fore.GREEN + "  --qps, -q            " + Fore.WHITE + "全局限速（每秒最大请求数），默认 " + Fore.YELLOW + "0" + Fore.WHITE + "（不限制），须为非负整数。")
    print(Fore.GREEN + "  --timeout, -t        " + Fore.WHITE + "单次查询超时（秒），默认 " + Fore.YELLOW + "5.0" + Fore.WHITE + " 秒，须为正数。")
    print(Fore.GREEN + "  --retries, -r        " + Fore.WHITE + "失败重试次数，默认 " + Fore.YELLOW + "0" + Fore.WHITE + " 次，须为非负整数。")
    print(Fore.GREEN + "  --logfile, -l        " + Fore.WHITE + "可选：指定日志文件路径，将 INFO 及以上日志写入文件；" + Fore.CYAN + "控制台只显示 WARNING+。")
    print()

    print(Fore.CYAN + "功能说明:")
    print(Fore.WHITE + "- 首先对目标服务器进行一次同步 ping，渲染并打印 MOTD：")
    print("    " + Fore.YELLOW + "带颜色的 MOTD 文本、在线/最大玩家数、服务端版本、Ping 延迟(ms)")
    print(Fore.WHITE + "- 然后使用多线程并发方式按给定参数进行 MOTD 查询压力测试。")
    print(Fore.WHITE + "- 压测分两个阶段显示进度：")
    print("    " + Fore.GREEN + "1. 提交中" + Fore.WHITE + "：将所有请求 Task 提交到线程池，实时显示“提交进度条”。")
    print("    " + Fore.GREEN + "2. 收集中" + Fore.WHITE + "：调用 as_completed 逐一收集结果，实时显示“收集中进度条”。")
    print(Fore.WHITE + "- 成功请求延迟只写入日志文件（若指定），不再输出到控制台；失败时会在控制台以红色提示。")
    print(Fore.WHITE + "- 支持 " + Fore.YELLOW + "Ctrl+C" + Fore.WHITE + " 随时中断，程序会统计并展示已完成的请求结果。")
    print()

    print(Fore.CYAN + "具体流程:")
    print(Fore.WHITE + "1. 检查并解析参数，进行基本校验。")
    print(Fore.WHITE + "2. 使用 mcstatus 对服务器执行一次 status（带 timeout），并调用 parse_motd 渲染 MOTD。")
    print(Fore.WHITE + "3. 显示服务器基本信息（彩色输出）。")
    print(Fore.WHITE + "4. 进入压测：创建 ThreadPoolExecutor 并发提交任务，")
    print("   每个任务调用 mcstatus.status() 获取 MOTD，超时/失败可重试 " + Fore.YELLOW + "--retries" + Fore.WHITE + " 次。")
    print(Fore.WHITE + "5. 在“提交中”阶段绘制绿色“█”进度条，实时反映已提交任务数。")
    print(Fore.WHITE + "6. 在“收集中”阶段同样绘制进度条，收集完成数并统计：")
    print("   - 成功：延迟数据保存在 stats，日志写入文件（INFO）。")
    print("   - 失败：在控制台输出红色提示（ERROR），同时写日志文件。")
    print(Fore.WHITE + "7. 全部完成或中断后，打印统计结果，包括：")
    print("   - 总请求数、成功数、失败数、成功率")
    print("   - 平均延迟、最小延迟、最大延迟、P99 延迟")
    print("   - 每秒请求数分布（REQ/s）")
    print()

    print(Fore.CYAN + "注意事项:")
    print(Fore.WHITE + "- 确保对目标服务器已获得管理员授权，避免被误判为恶意流量。")
    print(Fore.WHITE + "- 如果并发数和 QPS 设置太高，可能触发防火墙或 DDOS 防护机制。")
    print(Fore.WHITE + "- 建议在服务器低峰期进行测试，并监控服务器端 TPS、CPU、内存、网络带宽。")
    print(Fore.WHITE + "- 若需可视化分析，查看日志文件中的延迟数据，或后续绘图。")
    print(Fore.CYAN + "==========================================================")

def setup_logging(logfile: str = None):
    """
    配置日志：
      - 控制台 handler 只输出 WARNING 及以上。
      - 如果指定 logfile，则把 INFO 及以上都写入文件。
    返回 logger 对象。
    """
    logger = logging.getLogger("motd_stress")
    logger.setLevel(logging.INFO)

    # 控制台 handler（WARNING 及以上）
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(ch)

    # 文件 handler（INFO 及以上）
    if logfile:
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)

    return logger

def ping_server(server: JavaServer, timeout: float):
    """
    同步 ping 一次服务器，获取 MOTD、在线人数与版本等信息。
    如果无法连接或超时，会抛出异常。
    """
    if "timeout" in server.status.__code__.co_varnames:
        status = server.status(timeout=timeout)
    else:
        status = server.status()
    description = status.description  # MOTD 文本
    players_online = status.players.online
    players_max = status.players.max
    version_name = status.version.name
    latency = status.latency  # 毫秒
    return description, players_online, players_max, version_name, latency

def query_motd_sync(server: JavaServer, timeout: float, retries: int, logger) -> float:
    """
    同步查询一次 MOTD 并返回耗时（毫秒）。如果请求失败或超时，会重试 `retries` 次。
    最后仍失败则抛出异常，由调用者统计为失败。
    成功日志写入文件，不输出到控制台；失败时 WARNING+ 会输出到控制台。
    """
    for attempt in range(retries + 1):
        try:
            start = time.monotonic()
            if "timeout" in server.status.__code__.co_varnames:
                status = server.status(timeout=timeout)
            else:
                status = server.status()
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info(f"请求成功，延迟：{elapsed_ms:.2f} ms")
            return elapsed_ms
        except Exception as e:
            if attempt < retries:
                logger.warning(f"查询失败（第 {attempt + 1} 次重试）：{e}")
                continue
            else:
                raise

def draw_progress(label: str, completed: int, total: int):
    """
    在一行内绘制绿色“█”进度条，并标注阶段标签（中文）。
    """
    bar_length = 40
    fraction = completed / total if total > 0 else 0
    filled_length = int(bar_length * fraction)
    filled_bar = Fore.GREEN + '█' * filled_length + Style.RESET_ALL
    empty_bar = ' ' * (bar_length - filled_length)
    percent = fraction * 100
    with progress_lock:
        sys.stdout.write(
            f"\r{label}: [{filled_bar}{empty_bar}] {completed}/{total} ({percent:5.1f}%)"
        )
        sys.stdout.flush()
        if completed == total:
            print()  # 完成后换行

def print_stats(collected_stats: dict, total_requests: int):
    """
    计算并打印统计信息：成功率、平均延迟、最大/最小延迟、P99 延迟等，以及每秒请求数分布（带颜色输出）。
    """
    success = collected_stats["success"]
    failure = collected_stats["failure"]
    latencies = collected_stats["latencies"]

    print(Fore.MAGENTA + "\n======= 当前统计结果 =======")
    print(Fore.YELLOW + f"已完成请求数   : {total_requests}")
    print(Fore.GREEN + f"成功请求数     : {success}")
    print(Fore.RED + f"失败请求数     : {failure}")
    success_rate = (success / total_requests * 100) if total_requests > 0 else 0
    print(Fore.CYAN + f"成功率         : {success_rate:.2f}%")

    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)
        lat_sorted = sorted(latencies)
        p99 = lat_sorted[int(len(lat_sorted) * 0.99) - 1] if len(lat_sorted) >= 100 else lat_sorted[-1]
        print(Fore.YELLOW + f"平均延迟(ms)   : {avg_latency:.2f}")
        print(Fore.YELLOW + f"最小延迟(ms)   : {min_latency:.2f}")
        print(Fore.YELLOW + f"最大延迟(ms)   : {max_latency:.2f}")
        print(Fore.YELLOW + f"P99 延迟(ms)   : {p99:.2f}")
    else:
        print(Fore.RED + "无有效延迟数据（可能全部请求失败）")

    print(Fore.MAGENTA + "\n===== 每秒请求数 (REQ/s) =====")
    for sec in sorted(req_per_second):
        print(Fore.CYAN + f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(sec))} → {req_per_second[sec]} 次")

def main():
    parser = argparse.ArgumentParser(
        description="先 ping 显示 MOTD，再对 Minecraft 服务器进行压力测试（带颜色输出、绿色进度条，支持 Ctrl+C 中断）",
        epilog=(
            "如需查看帮助，请使用 -help。\n"
            "按 Ctrl+C 可随时中断并查看当前统计结果。\n"
        ),
        add_help=False
    )
    # 自定义 -help/--help 参数，打印彩色帮助
    parser.add_argument('-help', '--help', action='store_true', help='显示帮助信息并退出')

    # 其余参数均为中文提示
    parser.add_argument("--host", "-H", type=str, required=False, help="目标服务器地址或 IP（必填）")
    parser.add_argument("--port", "-P", type=int, default=25565, help="目标服务器端口，默认为 25565")
    parser.add_argument("--concurrency", "-c", type=int, default=50,
                        help="并发线程数（最大同时查询数量），默认 50，须为正整数")
    parser.add_argument("--total", "-n", type=int, required=False, help="总请求次数（必填），须为正整数")
    parser.add_argument("--qps", "-q", type=int, default=0, help="全局限速（每秒最大请求数），默认 0（不限制），须为非负整数")
    parser.add_argument("--timeout", "-t", type=float, default=5.0, help="单次查询超时（秒），默认 5 秒，须为正数")
    parser.add_argument("--retries", "-r", type=int, default=0, help="失败重试次数，默认 0 次，须为非负整数")
    parser.add_argument("--logfile", "-l", type=str, default="", help="可选：指定日志文件路径，将 INFO 及以上日志写入文件")

    # 如果用户只传了 -help 或 --help，就显示彩色帮助并退出
    if any(arg in ("-help", "--help") for arg in sys.argv[1:]):
        print_colored_help()
        sys.exit(0)

    args = parser.parse_args()

    # 参数校验
    if not args.host or args.total is None:
        print(Fore.RED + "[错误] 必须指定 --host 和 --total 参数。")
        print(Fore.CYAN + "使用 -help 查看帮助信息。")
        sys.exit(1)

    if args.concurrency <= 0 or args.total <= 0 or args.qps < 0 or args.timeout <= 0 or args.retries < 0:
        print(Fore.RED + "[错误] 参数校验失败：\n"
              "  • --concurrency、--total 必须为正整数；\n"
              "  • --qps、--retries 必须为非负整数；\n"
              "  • --timeout 必须为正数。")
        print(Fore.CYAN + "使用 -help 查看帮助信息。")
        sys.exit(1)

    host = args.host
    port = args.port
    concurrency = args.concurrency
    total = args.total
    qps = args.qps
    timeout = args.timeout
    retries = args.retries
    logfile = args.logfile

    # 设置日志
    logger = setup_logging(logfile if logfile else None)
    logger.info(f"启动压测：host={host}, port={port}, concurrency={concurrency}, "
                f"total={total}, qps={qps}, timeout={timeout}, retries={retries}, "
                f"logfile={logfile or '无'}")

    # 构造 JavaServer 对象
    try:
        server = JavaServer.lookup(f"{host}:{port}")  # 优先解析域名
        logger.info(f"域名 {host} 已解析并使用 IP 进行连接。")
    except Exception:
        server = JavaServer(host, port)
        logger.warning("域名解析失败或直接使用域名连接。")

    # 第一步：ping 服务器并渲染 MOTD 颜色
    print(Fore.CYAN + f"正在 ping {host}:{port} …")
    try:
        raw_motd, online, maximum, version_name, latency = ping_server(server, timeout)
        logger.info("Ping 成功")
        colored_motd = parse_motd(raw_motd)
        print(Fore.GREEN + "====== 服务器基本信息 ======")
        print(Fore.YELLOW + "MOTD             : " + colored_motd)
        print(Fore.YELLOW + f"在线玩家数       : {online}/{maximum}")
        print(Fore.YELLOW + f"服务端版本       : {version_name}")
        print(Fore.YELLOW + f"单次 ping 延迟   : {latency:.2f} ms")
        print(Fore.GREEN + "============================\n")
    except Exception as e:
        logger.error(f"ping 失败：{e}")
        print(Fore.RED + f"[错误] 无法 ping 到服务器 {host}:{port}，异常：{e}")
        print(Fore.RED + "请确认服务器地址、端口及网络可达性。")
        sys.exit(1)

    # 第二步：开始压力测试
    print(Fore.CYAN + f"开始对 {host}:{port} 进行 MOTD 压测，共 {total} 次请求，最大并发 {concurrency}，QPS 限制 {qps}")
    print(Fore.CYAN + "按 Ctrl+C 可随时中断并查看已完成统计\n")
    logger.info("进入压力测试阶段")

    # 如果 qps > 0，计算每次提交任务前的延迟（秒）
    delay_per_req = 1.0 / qps if qps > 0 else 0

    futures = []
    submitted = 0

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            start_time = time.monotonic()

            # 1. 提交所有请求任务，同时显示“提交中”进度条
            for i in range(total):
                if delay_per_req > 0:
                    time.sleep(delay_per_req)

                # 记录本次请求属于哪一个秒
                sec = int(time.time())
                req_per_second[sec] += 1

                # 提交任务
                future = executor.submit(query_motd_sync, server, timeout, retries, logger)
                futures.append(future)
                submitted += 1

                # 绘制“提交中”进度条
                draw_progress("提交中", submitted, total)

                # 每 500 次提交时，打印简要提示，不影响进度条
                if submitted % 500 == 0:
                    elapsed = time.monotonic() - start_time
                    print(Fore.YELLOW + f"\n[{time.strftime('%H:%M:%S')}] 已提交 {submitted}/{total} 次请求，用时 {elapsed:.2f} 秒")

            # 确保“提交中”阶段的进度条显示为 100%
            draw_progress("提交中", total, total)
            logger.info("所有请求提交完毕")

            # 2. 收集结果，并在同一行刷新“收集中”进度条
            completed = 0
            draw_progress("收集中", completed, total)
            for fut in as_completed(futures):
                try:
                    elapsed_ms = fut.result()
                    with stats_lock:
                        stats["success"] += 1
                        stats["latencies"].append(elapsed_ms)
                except Exception as e:
                    # 失败：先换行，再打印错误到控制台，最后重画进度条
                    print()
                    print(Fore.RED + f"[错误] {time.strftime('%H:%M:%S')} 查询失败：{e}")
                    draw_progress("收集中", completed, total)
                    logger.error(f"查询失败：{e}")
                    with stats_lock:
                        stats["failure"] += 1
                else:
                    # 成功：只写日志文件，不打印到控制台
                    with stats_lock:
                        stats["success"] += 1
                completed += 1
                draw_progress("收集中", completed, total)

    except KeyboardInterrupt:
        # 捕获 Ctrl+C：停止提交并收集已完成的任务
        print(Fore.RED + "\n检测到 Ctrl+C 中断，停止提交新任务并只汇总已完成任务结果...")
        logger.warning("用户通过 Ctrl+C 中断")

        # 等待短暂停顿，确保正在运行的任务有机会完成
        time.sleep(0.1)

        done_count = 0
        for fut in futures:
            if fut.done():
                try:
                    elapsed_ms = fut.result()
                    with stats_lock:
                        stats["success"] += 1
                        stats["latencies"].append(elapsed_ms)
                except Exception:
                    with stats_lock:
                        stats["failure"] += 1
                done_count += 1

        # 在中断时绘制“提交中”和“收集中”进度条
        draw_progress("提交中", total if submitted >= total else submitted, total)
        draw_progress("收集中", done_count, total)
        print_stats(stats, done_count)
        logger.info("中断时统计已完成任务结果")
        sys.exit(0)

    # 正常完成所有任务后，绘制满进度条并打印最终统计
    draw_progress("提交中", total, total)
    draw_progress("收集中", total, total)
    total_requests = stats["success"] + stats["failure"]
    print_stats(stats, total_requests)
    logger.info("压测结束，打印统计结果")


if __name__ == "__main__":
    main()
