#!/usr/bin/env python3
import argparse
import csv
import os
import time
from typing import Dict, List

import numpy as np

"""读取 driver 生成的 progress.csv 并可视化训练曲线。

支持两种模式：
1. 单次绘图（默认）
2. 实时刷新（--live），适合边训练边看趋势
"""


def _load_rows(csv_path: str) -> List[Dict[str, float]]:
    # 读 CSV 并把每列尽量转成 float，失败则记为 NaN。
    if not os.path.exists(csv_path):
        return []

    rows: List[Dict[str, float]] = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed: Dict[str, float] = {}
            for k, v in row.items():
                if v is None or v == "":
                    parsed[k] = np.nan
                    continue
                try:
                    parsed[k] = float(v)
                except ValueError:
                    parsed[k] = np.nan
            rows.append(parsed)
    return rows


def _moving_average(y: np.ndarray, window: int) -> np.ndarray:
    # 简单滑动平均，用于平滑波动较大的训练曲线。
    if window <= 1 or len(y) < 2:
        return y.copy()
    w = min(window, len(y))
    kernel = np.ones(w, dtype=np.float64) / float(w)
    valid = np.convolve(y, kernel, mode="valid")
    prefix = np.full(len(y) - len(valid), np.nan, dtype=np.float64)
    return np.concatenate([prefix, valid], axis=0)


def _arr(rows: List[Dict[str, float]], key: str) -> np.ndarray:
    # 从按行字典列表中抽取指定列为 NumPy 数组。
    return np.array([r.get(key, np.nan) for r in rows], dtype=np.float64)


def _plot_metric(ax, x, y, smooth_w, title, color):
    # 在同一张子图里画原始曲线 + 平滑曲线。
    if np.all(np.isnan(y)):
        ax.set_title(title)
        ax.grid(True, alpha=0.25)
        return
    ys = _moving_average(y, smooth_w)
    ax.plot(x, y, color=color, alpha=0.25, linewidth=1.0, label="raw")
    ax.plot(x, ys, color=color, linewidth=2.0, label=f"ma{smooth_w}")
    ax.set_title(title)
    ax.grid(True, alpha=0.25)


def _has_display() -> bool:
    # 判断当前环境是否有图形显示（本地桌面/Wayland）。
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _render(rows, args, fig, axes):
    # 把当前 rows 渲染到 2x3 子图网格。
    if len(rows) == 0:
        return False

    if args.tail > 0 and len(rows) > args.tail:
        rows = rows[-args.tail:]

    episode = _arr(rows, "episode")
    updates = _arr(rows, "updates")
    x = updates if not np.all(np.isnan(updates)) else episode
    x_label = "updates" if not np.all(np.isnan(updates)) else "episode"

    for ax in axes.flat:
        ax.clear()

    _plot_metric(axes[0, 0], x, _arr(rows, "reward"), args.smooth, "reward", "#2a9d8f")

    explored = _arr(rows, "explored_rate")
    success = _arr(rows, "success_rate")
    axes[0, 1].plot(x, _moving_average(explored, args.smooth), color="#1d3557", linewidth=2.0, label="explored_rate")
    axes[0, 1].plot(x, _moving_average(success, args.smooth), color="#e76f51", linewidth=2.0, label="success_rate")
    axes[0, 1].set_ylim(-0.05, 1.05)
    axes[0, 1].set_title("exploration/success")
    axes[0, 1].grid(True, alpha=0.25)
    axes[0, 1].legend(loc="best", fontsize=8)

    _plot_metric(axes[0, 2], x, _arr(rows, "travel_dist"), args.smooth, "travel_dist", "#f4a261")
    _plot_metric(axes[1, 0], x, _arr(rows, "policy_loss"), args.smooth, "policy_loss", "#8ab17d")
    _plot_metric(axes[1, 1], x, _arr(rows, "q_value_loss"), args.smooth, "q_value_loss", "#457b9d")

    mem_alloc = _arr(rows, "gpu_mem_alloc_gb")
    mem_resv = _arr(rows, "gpu_mem_reserved_gb")
    axes[1, 2].plot(x, _moving_average(mem_alloc, args.smooth), color="#6a4c93", linewidth=2.0, label="alloc_gb")
    axes[1, 2].plot(x, _moving_average(mem_resv, args.smooth), color="#ff6b6b", linewidth=2.0, label="reserved_gb")
    axes[1, 2].set_title("gpu_mem_gb")
    axes[1, 2].grid(True, alpha=0.25)
    axes[1, 2].legend(loc="best", fontsize=8)

    for ax in axes[1, :]:
        ax.set_xlabel(x_label)

    last = rows[-1]
    fig.suptitle(
        "DRL Training Progress | "
        f"ep={int(last.get('episode', np.nan)) if not np.isnan(last.get('episode', np.nan)) else 'nan'} "
        f"upd={int(last.get('updates', np.nan)) if not np.isnan(last.get('updates', np.nan)) else 'nan'} "
        f"reward={last.get('reward', np.nan):.3f} "
        f"explored={last.get('explored_rate', np.nan):.3f} "
        f"success={last.get('success_rate', np.nan):.3f}"
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return True


def main():
    parser = argparse.ArgumentParser(description="Plot training progress.csv with optional live refresh.")
    parser.add_argument(
        "--csv",
        default="train/ariadne1_ground_truth_critic/progress.csv",
        help="Path to progress.csv",
    )
    parser.add_argument("--smooth", type=int, default=20, help="Moving average window.")
    parser.add_argument("--refresh", type=float, default=2.0, help="Refresh seconds in live mode.")
    parser.add_argument("--tail", type=int, default=1000, help="Only plot last N rows (0 means all).")
    parser.add_argument("--live", action="store_true", help="Keep refreshing until Ctrl+C.")
    parser.add_argument("--save", default="", help="Optional path to save png (updated every refresh).")
    parser.add_argument("--no-show", action="store_true", help="Do not open window, useful for ssh/headless.")
    args = parser.parse_args()

    show_window = (not args.no_show) and _has_display()
    if not show_window:
        import matplotlib
        matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(16, 8))
    if show_window:
        plt.ion()

    last_count = -1
    try:
        while True:
            rows = _load_rows(args.csv)
            if len(rows) != last_count:
                last_count = len(rows)
                if len(rows) > 0:
                    last = rows[-1]
                    print(
                        f"[Progress] rows={len(rows)} ep={int(last.get('episode', np.nan)) if not np.isnan(last.get('episode', np.nan)) else 'nan'} "
                        f"reward={last.get('reward', np.nan):.4f} explored={last.get('explored_rate', np.nan):.4f} "
                        f"success={last.get('success_rate', np.nan):.4f}"
                    )
                else:
                    print(f"[Progress] waiting for data in: {args.csv}")

            ok = _render(rows, args, fig, axes)
            if ok and args.save:
                os.makedirs(os.path.dirname(args.save) or ".", exist_ok=True)
                fig.savefig(args.save, dpi=150)

            if show_window:
                plt.pause(max(args.refresh, 0.2))
            elif args.live:
                time.sleep(max(args.refresh, 0.2))

            if not args.live:
                break

    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
