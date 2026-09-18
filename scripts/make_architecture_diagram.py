"""Render the FTI architecture diagram as a PNG.

The MS1 proposal requires the diagram EMBEDDED AS AN IMAGE (not ASCII, not a link),
and MS4 requires one in the README. Generating it from code means it stays in sync
with the stack and can be regenerated whenever a component changes.

    python scripts/make_architecture_diagram.py --out docs/src/architecture.png
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.path import Path

INK = "#1a1a1a"
MUTED = "#6b6b6b"
PIPE_FILL = "#eef2f7"
PIPE_EDGE = "#4a6fa5"
STORE_FILL = "#f6f0e8"
STORE_EDGE = "#b08945"
EDGE_FILL = "#ffffff"


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def draw_box(ax, box: Box, title: str, subtitle: str = "", *, fill, edge, bold_size=10.5):
    ax.add_patch(
        FancyBboxPatch(
            (box.x, box.y),
            box.w,
            box.h,
            boxstyle="round,pad=0.004,rounding_size=0.012",
            linewidth=1.3,
            edgecolor=edge,
            facecolor=fill,
            zorder=2,
        )
    )
    ty = box.cy + (0.022 if subtitle else 0.0)
    ax.text(
        box.cx,
        ty,
        title,
        ha="center",
        va="center",
        fontsize=bold_size,
        fontweight="bold",
        color=INK,
        zorder=3,
    )
    if subtitle:
        ax.text(
            box.cx,
            box.cy - 0.030,
            subtitle,
            ha="center",
            va="center",
            fontsize=7.8,
            color=MUTED,
            zorder=3,
        )


def arrow(ax, start, end, label="", *, rad=0.0, color=INK, label_offset=(0, 0.022), fontsize=7.6):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            connectionstyle=f"arc3,rad={rad}",
            arrowstyle="-|>,head_width=3.4,head_length=6.5",
            linewidth=1.15,
            color=color,
            zorder=4,
            shrinkA=2,
            shrinkB=2,
        )
    )
    if label:
        mx = (start[0] + end[0]) / 2 + label_offset[0]
        my = (start[1] + end[1]) / 2 + label_offset[1]
        ax.text(
            mx,
            my,
            label,
            ha="center",
            va="center",
            fontsize=fontsize,
            color=MUTED,
            zorder=5,
            bbox=dict(boxstyle="round,pad=0.18", fc=EDGE_FILL, ec="none"),
        )


def build(args) -> None:
    fig, ax = plt.subplots(figsize=(12.6, 5.4), dpi=args.dpi)
    ax.set_xlim(0, 1)
    ax.set_ylim(0.035, 0.995 if args.title else 0.885)
    ax.axis("off")

    row_y, row_h = 0.60, 0.165
    src = Box(0.015, row_y, 0.135, row_h)
    feat = Box(0.195, row_y, 0.175, row_h)
    train = Box(0.415, row_y, 0.175, row_h)
    infer = Box(0.635, row_y, 0.175, row_h)
    ui = Box(0.865, row_y, 0.120, row_h)

    store_y, store_h = 0.235, 0.145
    fstore = Box(0.235, store_y, 0.205, store_h)
    mreg = Box(0.500, store_y, 0.205, store_h)

    draw_box(ax, src, args.source_title, args.source_subtitle, fill="#ffffff", edge=MUTED)
    draw_box(ax, feat, "1  Feature pipeline", args.feature_sub, fill=PIPE_FILL, edge=PIPE_EDGE)
    draw_box(ax, train, "2  Training pipeline", args.training_sub, fill=PIPE_FILL, edge=PIPE_EDGE)
    draw_box(ax, infer, "3  Inference pipeline", args.inference_sub, fill=PIPE_FILL, edge=PIPE_EDGE)
    draw_box(ax, ui, "UI", args.ui_sub, fill="#ffffff", edge=MUTED, bold_size=10)

    draw_box(
        ax,
        fstore,
        "Feature Store",
        args.feature_store,
        fill=STORE_FILL,
        edge=STORE_EDGE,
        bold_size=10,
    )
    draw_box(
        ax,
        mreg,
        "Model Registry",
        args.model_registry,
        fill=STORE_FILL,
        edge=STORE_EDGE,
        bold_size=10,
    )

    for box, text in (
        (feat, args.feature_trigger),
        (train, args.training_trigger),
        (infer, args.inference_trigger),
    ):
        ax.text(
            box.cx,
            row_y + row_h + 0.052,
            text,
            ha="center",
            va="center",
            fontsize=8.0,
            color=MUTED,
            style="italic",
        )

    y_mid = row_y + row_h / 2

    # The ONLY horizontal arrows are into the system and out of it. The three
    # pipelines are deliberately NOT connected to each other: they are decoupled
    # and communicate solely through the feature store and the model registry.
    arrow(ax, (src.x + src.w, y_mid), (feat.x, y_mid))
    arrow(ax, (infer.x + infer.w, y_mid), (ui.x, y_mid))

    top_f = fstore.y + store_h
    top_m = mreg.y + store_h
    arrow(
        ax,
        (feat.cx - 0.012, row_y),
        (fstore.cx - 0.030, top_f),
        "write",
        label_offset=(-0.050, 0.004),
    )
    arrow(
        ax,
        (fstore.cx + 0.045, top_f),
        (train.cx - 0.020, row_y),
        "read",
        label_offset=(-0.058, 0.004),
    )
    arrow(
        ax,
        (train.cx + 0.012, row_y),
        (mreg.cx - 0.030, top_m),
        "register",
        label_offset=(0.058, 0.004),
    )
    arrow(
        ax,
        (mreg.cx + 0.045, top_m),
        (infer.cx - 0.020, row_y),
        "load best",
        label_offset=(0.056, 0.004),
    )

    # Feature store -> inference pipeline, routed along the bottom so it crosses
    # nothing. This is the edge students most often forget: serving needs the same
    # features the model was trained on, read at inference time.
    y_low = 0.085
    x_up = infer.cx + 0.045
    verts = [(fstore.cx, fstore.y), (fstore.cx, y_low), (x_up, y_low), (x_up, row_y)]
    codes = [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO]
    ax.add_patch(
        FancyArrowPatch(
            path=Path(verts, codes),
            arrowstyle="-|>,head_width=3.4,head_length=6.5",
            linewidth=1.15,
            color=INK,
            zorder=4,
            shrinkA=2,
            shrinkB=2,
        )
    )
    ax.text(
        (fstore.cx + x_up) / 2,
        y_low,
        "features at inference time",
        ha="center",
        va="center",
        fontsize=7.8,
        color=MUTED,
        zorder=5,
        bbox=dict(boxstyle="round,pad=0.25", fc=EDGE_FILL, ec="none"),
    )

    if args.title:
        ax.text(
            0.5, 0.985, args.title, ha="center", va="top", fontsize=12, fontweight="bold", color=INK
        )

    fig.savefig(args.out, bbox_inches="tight", facecolor="white", pad_inches=0.16)
    print(f"wrote {args.out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="docs/src/architecture.png")
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--title", default="")
    p.add_argument("--source-title", default="Live data")
    p.add_argument("--source-subtitle", default="API · scraping")
    p.add_argument("--feature-sub", default="ingest · compute · write")
    p.add_argument("--training-sub", default="train · evaluate · register")
    p.add_argument("--inference-sub", default="load model · predict")
    p.add_argument("--ui-sub", default="")
    p.add_argument("--feature-store", default="Hopsworks")
    p.add_argument("--model-registry", default="MLflow")
    p.add_argument("--feature-trigger", default="schedule / streaming · backfill")
    p.add_argument("--training-trigger", default="triggered / manual")
    p.add_argument("--inference-trigger", default="on demand (UI) / schedule")
    build(p.parse_args())


if __name__ == "__main__":
    main()
