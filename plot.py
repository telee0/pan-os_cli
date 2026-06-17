"""

pan-os-cli v2.3 [20260617]

Script to repeat CLI commands on PAN-OS over SSH

by Terence LEE <telee.hk@gmail.com>

https://github.com/telee0/pan-os_cli

"""

import os
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

cf = {
    'job_dir': 'job-{}',
    'src_dir': 'data',
    'source': ['p[34]-*.png', 'p[12]-*.png'],
    'target': 'combined-{}.png',
    'grid_size': (2, 2),

    'traffic_analysis': True,
    'log_csv': 'log.csv',
    'tra_apps_top_k': 20,
    'tra_app_filter': [],
    'tra_bins': {
        'bytes': (
            [0, 5e2, 1e3, 16e3, 64e3, 1e6, 4e6, 1e8, 1e9],  # avoid 1024**2, 1024**3, etc.
            ['0', '500', '1K', '16K', '64K', '1M', '4M', '100M', '1G'],
        ),
        'elapsed': (
            [0, 1, 3, 10, 30, 60, 180, 300, 1800, 3600, 86400],
            ['0', '1s', '3s', '10s', '30s', '1m', '3m', '5m', '30m', '1h', '24h'],
        ),
    },
    'tra_csv_file': 'tra.csv',
    'tra_plot_file': 't{0}-{1}.png',
    'tra_plot_file_combined': 't-{0}.png',  # combined plot file names
    'tra_plot_grid_size': (2, 2),  # grid size (rows, columns) of combined plots
}

ctx = {
    'start_time': datetime.now(),
}

def init():
    src_dir = Path(cf['src_dir'])
    files = []
    for pattern in cf['source']:
        for file in src_dir.glob(pattern):
            path = Path(file)
            files.append(path)
    files_sorted = sorted(
        files,
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files_sorted:
        print("Error: No files matched.", file=sys.stderr)
        # sys.exit(1)
    ctx['source'] = files_sorted

    start_time = ctx['start_time']
    ddhhmm = start_time.strftime('%d%H%M')
    job_dir = cf['job_dir'].format(ddhhmm)
    os.makedirs(job_dir, exist_ok=True)
    ctx['target'] = str(Path(job_dir) / cf['target'])

    log_csv = src_dir / cf['log_csv']
    if log_csv.is_file():
        ctx["log_csv"] = log_csv
    ctx['tra_plot_file'] = str(Path(job_dir) / cf['tra_plot_file'])
    ctx['tra_plot_file_combined'] = str(Path(job_dir) / cf['tra_plot_file_combined'])



def combine_plots(source, target, grid_size=(1,1), start=0, watermark=None, shift=0.0):
    n_plots = len(source)
    n_rows, n_cols = grid_size

    if n_rows * n_cols <= 1 or n_plots <= 1:
        return

    # ctx['log'].info(f"creating plot grid from {n_plots} plots")

    for i in range(0, n_plots, n_rows * n_cols):
        plot_file_combined = target.format(start + i)
        fig, axs = plt.subplots(n_rows, n_cols, figsize=(n_cols * 6, n_rows * 4))
        axs = axs.flatten()
        n = min(i + n_rows * n_cols, n_plots)
        for j in range(i, n):
            plot_file = source[j]
            image = plt.imread(plot_file)
            ax = axs[j-i]
            ax.imshow(image)
            ax.axis('off')
            if watermark:
                label = watermark[j]
                ax.text(
                    0.5 + shift, 0.5, label,
                    transform=ax.transAxes,
                    fontsize=25,
                    color='black', alpha=0.1,
                    # color='white', alpha=0.5, bbox=dict(facecolor='black', alpha=0.1, edgecolor='none'),
                    ha='center', va='center',
                    weight='bold',
                    rotation=10
                )
        for j in range(n, i + n_rows * n_cols):
            axs[j-i].axis('off')
        plt.tight_layout()
        plt.savefig(plot_file_combined)
        plt.close()

        # ctx['log'].info(f"combined plot {plot_file_combined} saved")


def plot_logs_traffic(df):
    if 'traffic_analysis' not in cf or not cf['traffic_analysis']:
        return

    # ctx['log'].info(f"plotting traffic stats..")

    colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
    n_colors = len(colors)

    plot_files, watermark = [], []
    plot_file_combined = ctx['tra_plot_file_combined']
    grid_size = cf['tra_plot_grid_size']

    stats = df.groupby("app").agg(
        bytes_sum=("bytes", "sum"),
        elapsed_sum=("elapsed", "sum"),
        sess_count=("app", "count")
    )
    stats["bytes_avg"] = (stats["bytes_sum"] / stats["sess_count"])
    stats["elapsed_avg"] = (stats["elapsed_sum"] / stats["sess_count"])

    data = {
        'sess_count': ('topAppsByLogCount', 'Count'),
        'bytes_sum': ('topAppsByBytesSum', 'Bytes'),
        'elapsed_sum': ('topAppsByElapsedSum', 'Seconds'),
        'bytes_avg': ('topAppsByBytesAvg', 'Bytes'),
        'elapsed_avg': ('topAppsByElapsedAvg', 'Seconds'),
    }

    top_k = cf['tra_apps_top_k']

    for i, column in enumerate(data.keys()):
        title, xlabel = data[column]

        plot_file = ctx['tra_plot_file'].format(i, title)

        apps = stats[column].sort_values(ascending=False).head(top_k).sort_values()

        fig, ax = plt.subplots(figsize=(10, 5))

        y_pos = range(len(apps))

        color = colors[i % n_colors]

        ax.barh(
            y_pos,
            apps.values,
            color=color,  # "#4C72B0",  # simple seaborn-like blue
            edgecolor="grey",  # "dimgray",
            linewidth=0.8,
            alpha=0.9
        )

        ax.set_yticks(y_pos)
        ax.set_yticklabels(apps.index)

        max_v = apps.max()

        for j, (val) in enumerate(apps.values):
            ax.text(
                val + max_v * 0.01,  # right of bar
                j,
                f"{val:,.0f}",
                va="center", ha="left",
                fontsize=9,
                fontweight="bold"
            )

        ax.set_xlim(0, max_v * 1.2)

        ax.grid(axis="x", linestyle="--", alpha=0.4)

        ax.set_title(f"{title} (k={top_k}) ")
        ax.set_xlabel(xlabel)

        plt.tight_layout()
        plt.savefig(plot_file)
        plt.close()

        # ctx['log'].info(f"plot {plot_file} saved")

        plot_files.append(plot_file)
        watermark.append(title)

    combine_plots(plot_files, plot_file_combined, grid_size=grid_size, watermark=watermark, shift=0.2)
    plot_files, watermark = [], []

    # distribution of column values like bytes and elapsed
    #
    for i, column in enumerate(cf['tra_bins'].keys(), start=len(data)):
        title = column.title()
        xlabel = title

        plot_file = ctx['tra_plot_file'].format(i, title)

        bins, labels = cf['tra_bins'][column]

        plt.figure(figsize=(10, 5))

        color = colors[i % n_colors]

        ax = sns.histplot(
            df[column],
            bins=bins,
            color=color,
            edgecolor="grey",  # "dimgray",  # "black",
            linewidth=1.0,
            alpha=0.4
        )

        ax.set_title(f"Traffic Log Distribution - {title}")
        ax.set_xlabel(xlabel)
        ymax = ax.get_ylim()[1]
        ax.set_ylim(0, ymax * 1.25)

        plt.xscale("log")

        for j, p in enumerate(ax.patches):
            h = p.get_height()

            if h <= 0:
                continue

            left = labels[j]
            if j < len(labels) - 1:
                right = labels[j + 1]
                label = f"{left}-{right}"
            else:
                label = f"> {left}"

            x = p.get_x() + p.get_width()

            if h > 0:
                ax.text(
                    x,
                    h * 1.05,
                    f"{int(h):,}\n{label}",
                    ha="right", va="bottom",
                    fontsize=8
                )

        plt.grid(True, which="both", axis="both", linestyle="--", alpha=0.3)

        plt.tight_layout()
        plt.savefig(plot_file)
        plt.close()

        # ctx['log'].info(f"plot {plot_file} saved")

        plot_files.append(plot_file)
        watermark.append(title)

    combine_plots(plot_files, plot_file_combined, grid_size=grid_size, watermark=watermark, start=len(data))


def demo_combine_plots():
    init()
    watermark = []
    for s in ctx['source']:
        watermark.append(s.stem.split('-')[1])
    combine_plots(ctx['source'], ctx['target'], grid_size=cf['grid_size'], watermark=watermark)


def demo_plot_logs_traffic():
    init()
    if 'log_csv' in ctx:
        df = pd.read_csv(ctx["log_csv"])
    df = df.rename(columns={
        "Application": "app",
        "Bytes": "bytes",
        "Elapsed Time (sec)": "elapsed",
    })
    for col in df.columns:
        print(col)
    plot_logs_traffic(df)


if __name__ == '__main__':
    demo_plot_logs_traffic()
