import os
import sys
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt

cf = {
    'job_dir': 'job-{}',
    'src_dir': 'job-072218-192.168.2.233',
    'source': ['p[34]-*.png', 'p[12]-*.png'],
    'target': 'combined-{}.png',
    'grid_size': (2, 2),
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
        sys.exit(1)
    ctx['source'] = files_sorted

    start_time = ctx['start_time']
    ddhhmm = start_time.strftime('%d%H%M')
    job_dir = cf['job_dir'].format(ddhhmm)
    os.makedirs(job_dir, exist_ok=True)
    ctx['target'] = str(Path(job_dir) / cf['target'])


def combine_plots(source, target, grid_size=(1,1), watermark=None):
    n_plots = len(source)
    n_rows, n_cols = grid_size

    if n_rows * n_cols <= 1 or n_plots <= 1:
        return

    # ctx['log'].info(f"creating plot grid from {n_plots} plots")

    for i in range(0, n_plots, n_rows * n_cols):
        plot_file_combined = target.format(i)
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
                    0.5, 0.5, label,
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

def go():
    init()
    watermark = []
    for s in ctx['source']:
        watermark.append(s.stem.split('-')[1])
    combine_plots(ctx['source'], ctx['target'], grid_size=cf['grid_size'], watermark=watermark)


if __name__ == '__main__':
    go()
