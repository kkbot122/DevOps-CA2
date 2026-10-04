#!/usr/bin/env python3
"""Build the evidence-led five-slide Shortly report deck."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ensure_pptx_runtime() -> None:
    if importlib.util.find_spec("pptx"):
        return
    runtime = (
        Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
    )
    if runtime.exists() and str(runtime) != sys.executable:
        os.execv(str(runtime), [str(runtime), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit("python-pptx is required; install requirements-report.txt and retry.")


ensure_pptx_runtime()

from PIL import Image  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE  # noqa: E402
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN  # noqa: E402
from pptx.util import Inches, Pt  # noqa: E402

OUT = ROOT / "report"
SHOT = ROOT / "docs" / "screenshots"
SLIDE_W = 13.333
SLIDE_H = 7.5
NAVY = "172B3A"
INK = "18313F"
TEAL = "1A8C8C"
LIGHT = "EEF4F5"
MID = "D2E2E5"
GRAY = "60727C"
WHITE = "FFFFFF"
AMBER = "C07A1A"
FONT = "Arial"


def rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


def add_text(slide, text, x, y, w, h, size=14, color=INK, bold=False, align=None, margin=0.04):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(margin)
    frame.margin_right = Inches(margin)
    frame.margin_top = Inches(margin)
    frame.margin_bottom = Inches(margin)
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]
    if align is not None:
        paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = rgb(color)
    return box


def add_box(slide, text, x, y, w, h, fill=LIGHT, line=MID, color=INK, size=14, bold=False):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    shape.line.color.rgb = rgb(line)
    shape.line.width = Pt(1.15)
    shape.text_frame.clear()
    shape.text_frame.word_wrap = True
    shape.text_frame.margin_left = Inches(0.08)
    shape.text_frame.margin_right = Inches(0.08)
    shape.text_frame.margin_top = Inches(0.04)
    shape.text_frame.margin_bottom = Inches(0.04)
    shape.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = shape.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = rgb(color)
    return shape


def add_line(slide, x1, y1, x2, y2, color=TEAL, width=1.8):
    line = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)
    )
    line.line.color.rgb = rgb(color)
    line.line.width = Pt(width)
    line.line.end_arrowhead = True
    return line


def add_header(slide, title, subtitle):
    add_text(slide, title, 0.52, 0.28, 12.2, 0.56, 29, NAVY, True)
    slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(0.98), Inches(0.82), Inches(0.06)
    ).fill.solid()
    accent = slide.shapes[-1]
    accent.fill.fore_color.rgb = rgb(TEAL)
    accent.line.fill.background()
    add_text(slide, subtitle, 0.54, 1.06, 12.2, 0.36, 14, GRAY)


def add_footer(slide, number):
    add_text(slide, "Shortly DevOps · CA2 · <Group members>", 0.55, 7.12, 10.8, 0.18, 9, GRAY)
    add_text(slide, str(number), 12.25, 7.1, 0.45, 0.2, 10, GRAY, align=PP_ALIGN.RIGHT)


def add_notes(slide, text):
    notes = slide.notes_slide.notes_text_frame
    notes.text = text


def add_capture_slot(slide, filename, x, y, w, h, caption):
    path = SHOT / filename
    if path.is_file():
        with Image.open(path) as image_file:
            image_ratio = image_file.width / image_file.height
        frame_ratio = w / h
        if image_ratio > frame_ratio:
            picture_w = w
            picture_h = w / image_ratio
        else:
            picture_h = h
            picture_w = h * image_ratio
        picture_x = x + (w - picture_w) / 2
        picture_y = y + (h - picture_h) / 2
        slide.shapes.add_picture(
            str(path),
            Inches(picture_x),
            Inches(picture_y),
            width=Inches(picture_w),
            height=Inches(picture_h),
        )
        border = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
        )
        border.fill.background()
        border.line.color.rgb = rgb(MID)
        border.line.width = Pt(1)
        print(f"EMBEDDED: {filename}")
    else:
        frame = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
        )
        frame.fill.solid()
        frame.fill.fore_color.rgb = rgb("F6F8F9")
        frame.line.color.rgb = rgb(GRAY)
        frame.line.width = Pt(1)
        add_text(
            slide,
            f"SCREENSHOT PENDING: {filename}",
            x + 0.12,
            y + h / 2 - 0.17,
            w - 0.24,
            0.36,
            12,
            GRAY,
            True,
            PP_ALIGN.CENTER,
        )
        print(f"PLACEHOLDER: {filename}")
    add_text(slide, caption, x, y + h + 0.02, w, 0.28, 14, INK, True)


def slide_architecture(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(
        slide,
        "Shortly keeps request state in Redis and releases under observation",
        "Shortly · URL short links · FastAPI / Redis / Minikube / Prometheus / Locust / Ansible",
    )
    add_box(slide, "User", 0.5, 2.1, 1.05, 0.72, WHITE, MID, size=15, bold=True)
    add_box(
        slide, "nginx Ingress\nshort.local", 1.85, 2.1, 1.52, 0.72, LIGHT, MID, size=14, bold=True
    )
    add_box(slide, "ClusterIP\nService", 3.68, 2.1, 1.3, 0.72, LIGHT, MID, size=14, bold=True)
    add_box(
        slide,
        "Shortly API pods\nHPA 2–5 · PDB min 1",
        5.3,
        1.86,
        2.12,
        1.2,
        "DDF0EF",
        TEAL,
        size=15,
        bold=True,
    )
    add_box(slide, "Redis\nshared state", 7.82, 2.1, 1.38, 0.72, LIGHT, MID, size=14, bold=True)
    add_box(slide, "1 Gi PVC\nAOF", 9.48, 2.1, 1.05, 0.72, WHITE, MID, size=14, bold=True)
    for x1, x2 in [(1.55, 1.85), (3.37, 3.68), (4.98, 5.3), (7.42, 7.82), (9.2, 9.48)]:
        add_line(slide, x1, 2.46, x2, 2.46)
    add_box(
        slide,
        "ServiceMonitor → Prometheus\nGrafana dashboard · Alertmanager",
        10.8,
        1.85,
        2.02,
        1.22,
        "EAF3F3",
        TEAL,
        size=14,
        bold=True,
    )
    add_line(slide, 6.36, 1.86, 6.36, 1.58, color=TEAL, width=1.2)
    add_line(slide, 6.36, 1.58, 10.8, 1.58, color=TEAL, width=1.2)
    add_line(slide, 10.8, 1.58, 10.8, 1.85, color=TEAL, width=1.2)
    add_box(
        slide,
        "GitHub Actions\nhosted checks → self-hosted deploy",
        1.1,
        4.02,
        3.75,
        0.82,
        "F2F5F7",
        MID,
        size=14,
        bold=True,
    )
    add_box(
        slide,
        "Ansible\nDebian / Ubuntu host configuration",
        5.08,
        4.02,
        3.5,
        0.82,
        "F2F5F7",
        MID,
        size=14,
        bold=True,
    )
    add_line(slide, 5.08, 4.43, 4.85, 4.43, color=GRAY, width=1.2)
    add_text(
        slide,
        "Key choices: stateless API + Redis · readiness checks Redis; liveness does not\n"
        "maxUnavailable: 0 · one Redis replica in this local demo",
        0.7,
        5.48,
        12.0,
        0.7,
        15,
        INK,
        True,
        PP_ALIGN.CENTER,
    )
    add_text(
        slide,
        "Metrics scrape the app Service; the local Alertmanager uses a null receiver.",
        0.7,
        6.3,
        12.0,
        0.34,
        14,
        GRAY,
        align=PP_ALIGN.CENTER,
    )
    add_footer(slide, 1)
    add_notes(
        slide,
        "Shortly is a small FastAPI URL shortener. A request enters through the local nginx "
        "Ingress, passes through a Kubernetes Service, and can reach either API pod. The API "
        "pods keep no link state locally; Redis stores links, click counts, rate limits, recent "
        "links, and shared demo controls. Redis writes use an append-only file on a persistent "
        "volume, although this project runs only one Redis replica. The HPA keeps at least two "
        "and can scale to five pods, while the PDB asks Kubernetes to keep one available during "
        "disruptions. Liveness checks whether the process is alive; readiness also checks Redis. "
        "Prometheus scrapes the service through a ServiceMonitor, Grafana displays the metrics, "
        "and Alertmanager evaluates the rules. GitHub Actions builds and scans releases, while "
        "Ansible configures the supported runner host. Point at the path from User through "
        "Ingress to Redis, then at the monitoring band and the two automation boxes.",
    )
    return slide


def slide_pipeline(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(
        slide,
        "A scanned image must pass local-cluster gates before it deploys",
        "Hosted checks protect builds; a guarded self-hosted runner updates Minikube.",
    )
    hosted = [
        ("Push", 0.52),
        ("Lint ∥ test", 3.55),
        ("Build image\nTrivy + SBOM", 6.58),
        ("Push to GHCR", 9.61),
    ]
    for label, x in hosted:
        add_box(slide, label, x, 1.74, 2.4, 0.84, "EAF3F3", TEAL, size=15, bold=True)
    for x in (2.98, 6.01, 9.04):
        add_line(slide, x, 2.16, x + 0.52, 2.16)
    add_text(slide, "GITHUB-HOSTED RUNNERS", 0.55, 1.43, 3.3, 0.25, 12, TEAL, True)
    local = [
        ("Preflight +\ncontext guard", 0.52),
        ("Verify image\ndigest", 3.55),
        ("Load + deploy\noverlay", 6.58),
        ("Rollout probes\nsmoke + version", 9.61),
    ]
    for label, x in local:
        add_box(slide, label, x, 3.12, 2.4, 0.9, "FFF7E9", AMBER, size=15, bold=True)
    for x in (2.98, 6.01, 9.04):
        add_line(slide, x, 3.57, x + 0.52, 3.57, color=AMBER)
    add_line(slide, 10.82, 2.58, 10.82, 2.91, color=GRAY, width=1.3)
    add_line(slide, 10.82, 2.91, 1.72, 2.91, color=GRAY, width=1.3)
    add_line(slide, 1.72, 2.91, 1.72, 3.12, color=GRAY, width=1.3)
    add_box(slide, "PASS → deployed", 7.05, 4.28, 2.45, 0.62, "EAF3F3", TEAL, size=14, bold=True)
    add_box(
        slide,
        "FAIL → automatic undo\nrelease job remains red",
        9.85,
        4.2,
        2.55,
        0.78,
        "FFF2E1",
        AMBER,
        size=14,
        bold=True,
    )
    add_line(slide, 11.1, 4.02, 8.27, 4.28, color=TEAL, width=1.2)
    add_line(slide, 11.8, 4.02, 11.1, 4.2, color=AMBER, width=1.2)
    add_text(
        slide,
        "Typical duration: 7–15 min (runbook estimate · docs/cicd.md)",
        0.55,
        4.45,
        5.8,
        0.35,
        14,
        INK,
        True,
    )
    add_capture_slot(slide, "10-pipeline-green.png", 0.55, 5.03, 5.85, 1.05, "Green workflow run")
    add_capture_slot(
        slide,
        "11-pipeline-autorollback.png",
        6.9,
        5.03,
        5.85,
        1.05,
        "Failed release with automatic rollback",
    )
    add_footer(slide, 2)
    add_notes(
        slide,
        "This workflow separates hosted checks from deployment to the local cluster. Lint and "
        "tests run in parallel. A successful build is scanned by Trivy and produces a CycloneDX "
        "software bill of materials; only then is the image pushed to GHCR. The self-hosted "
        "runner runs only on trusted main-branch release events, not pull requests. Before "
        "changing the cluster it checks the context and prerequisites, then pulls the image and "
        "verifies that its digest matches the hosted build. It loads that exact image, applies "
        "the CI overlay, waits for rollout probes, and verifies smoke requests and release "
        "version. A failure triggers automatic rollback, but the workflow remains red so the "
        "bad release is visible. The runbook estimates a typical pipeline takes seven to "
        "fifteen minutes; that is a documented estimate, not a measurement from GitHub history. "
        "Point from lint and tests through GHCR to preflight and digest verification, then show "
        "the success and rollback branches.",
    )
    return slide


def slide_evidence(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(
        slide,
        "Saved scenarios show resilience, with one suite caveat",
        "Committed load-test and Ansible evidence; missing UI captures remain pending.",
    )
    slots = [
        ("01-baseline-overview.png", "Grafana overview under baseline traffic"),
        ("17-rolling-update-probe.png", "Rolling update: v1 and v2 seen; 0 failures"),
        ("07-bad-release-crash.png", "CrashLoopBackOff observed, then rollback"),
        ("23-ansible-idempotent-recap.png", "Ansible second apply: changed=0"),
    ]
    positions = [(0.6, 1.72), (6.85, 1.72), (0.6, 3.47), (6.85, 3.47)]
    for (filename, caption), (x, y) in zip(slots, positions):
        add_capture_slot(slide, filename, x, y, 5.88, 1.16, caption)
    add_box(
        slide,
        "Saved run: 8/9 PASS, 1 FAIL; focused abuse rerun PASS\n"
        "Baseline 3,753 requests / 0 failures · "
        "Surge 2→3 replicas · full suite 55.7 min",
        0.64,
        5.6,
        12.05,
        0.85,
        "EAF3F3",
        TEAL,
        size=15,
        bold=True,
    )
    add_text(
        slide,
        "The full suite was not rerun after the focused abuse fix. "
        "Source: loadtest/reports/SUMMARY.md.",
        0.7,
        6.56,
        12,
        0.28,
        12,
        GRAY,
        align=PP_ALIGN.CENTER,
    )
    add_footer(slide, 3)
    add_notes(
        slide,
        "These are evidence slots, not simulated screenshots. The repository had no actual UI "
        "images when this deck was built, so the frames are pending and should be replaced only "
        "with real captures. The numbers come from saved results. The original full scenario run "
        "lasted 55.7 minutes and recorded eight passes and one failure: abuse. A later focused "
        "abuse rerun passed with 6,309 requests and no unexpected failures, but the complete "
        "suite was not rerun, so we should not claim nine out of nine for the full run. Baseline "
        "recorded 3,753 requests and zero unexpected failures. The surge test reached three "
        "replicas from a baseline of two and returned to two. The Ansible second application in "
        "the Ubuntu container changed zero items. Point at the four evidence types, then at the "
        "result line and explain the full-suite caveat.",
    )
    return slide


def slide_challenges(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(
        slide,
        "The hardest failures crossed component boundaries",
        "Top evidence-backed challenges · details and sources: docs/CHALLENGES.md",
    )
    rows = [
        "1  Ready probes missed release errors → health checks were too narrow → "
        "alert on 5xx and roll back",
        "2  Nested Kustomize base was blocked → path restriction → "
        "render a temporary sibling overlay",
        "3  Grafana OOM at 256/384 MiB → limits were too low → use the evidenced 512 MiB setting",
        "4  Redis outage broke readiness → API depends on Redis → "
        "separate liveness and verify recovery",
        "5  Ansible laptop was macOS → playbook supports Debian/Ubuntu → "
        "prove idempotence on Ubuntu 24.04",
    ]
    for i, row in enumerate(rows):
        y = 1.65 + i * 0.91
        add_box(
            slide,
            row,
            0.65,
            y,
            12.0,
            0.7,
            LIGHT if i % 2 == 0 else WHITE,
            MID,
            size=15,
            bold=(i == 0),
        )
    add_footer(slide, 4)
    add_notes(
        slide,
        "The first challenge is that Kubernetes readiness can stay green while an application "
        "returns errors on ordinary requests. The bad-release scenario showed this: the pods were "
        "Ready, the error alert fired, and rollback restored version one. The second challenge "
        "was packaging the Kubernetes deployment. The nested Kustomize overlay could not safely "
        "refer to its parent directory, so the deploy script generates a temporary sibling "
        "overlay, renders it, and applies the full result together. Third, Grafana was OOM-killed "
        "at two lower memory limits, so chart values were raised to 512 MiB. Fourth, Redis outage "
        "handling needed readiness to fall without restarting the API; the scenario confirmed "
        "zero app restarts and link recovery. Finally, the macOS machine was deliberately "
        "rejected by the Ubuntu/Debian-only Ansible playbook; positive proof came from Ubuntu "
        "24.04. Point at each problem-to-cause-to-fix line and tie it to its result or commit.",
    )
    return slide


def slide_lessons(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(
        slide,
        "We learned to verify behavior, not only health",
        "Each lesson links to the challenge log; production work is future work.",
    )
    lessons = [
        "#1  Readiness and user success are different signals; alert on real request outcomes.",
        "#2  Render the exact manifest set before applying; layout affects deploy tooling.",
        "#3  Resource limits need observed headroom; lower Grafana limits restarted the pod.",
        "#4  Dependency-aware readiness protects traffic without restarting the API process.",
        "#5  Idempotence needs a supported target; keep the macOS refusal distinct.",
    ]
    for i, line in enumerate(lessons):
        add_text(slide, line, 0.75, 1.7 + i * 0.7, 11.9, 0.42, 16, INK, bold=(i == 0))
    add_box(
        slide,
        "Next: use a multi-node cloud cluster; add SLO alerts, real alert routing and GitOps; "
        "isolate the self-hosted runner.",
        0.7,
        5.48,
        12.0,
        0.88,
        "EAF3F3",
        TEAL,
        size=15,
        bold=True,
    )
    add_footer(slide, 5)
    add_notes(
        slide,
        "The project taught us to verify what users experience, not only whether containers are "
        "running. In the silent error release, probes passed but a request-error alert caught "
        "the fault. For Kubernetes packaging, deployment tooling should render exactly the set it "
        "will apply. Resource limits need evidence because Grafana restarted under two lower "
        "limits. Readiness should reflect dependency availability, while liveness should avoid "
        "restarting an API process that can recover when Redis returns. Ansible results belong "
        "to the supported OS: the Mac was refused safely, and the positive run used Ubuntu "
        "24.04. Next I would use a multi-node cloud cluster, base alerts on service objectives, "
        "route alerts to a real receiver, and isolate the self-hosted runner. Point at the "
        "challenge numbers beside each lesson, then the future-work box.",
    )
    return slide


def write_diagram_assets() -> None:
    assets = OUT / "assets"
    style = (
        "<style>text{font-family:Arial,sans-serif;fill:#18313F}"
        ".node{fill:#EEF4F5;stroke:#1A8C8C;stroke-width:2}"
        ".local{fill:#FFF7E9;stroke:#C07A1A;stroke-width:2}"
        ".link{stroke:#1A8C8C;stroke-width:3;marker-end:url(#arrow)}</style>"
    )
    marker = (
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" '
        'refX="8" refY="3" orient="auto">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#1A8C8C"/></marker></defs>'
    )
    architecture_nodes = [
        (30, "User"),
        (190, "Ingress"),
        (350, "Service"),
        (510, "Shortly API pods"),
        (700, "Redis"),
        (860, "AOF PVC"),
        (1020, "Prometheus / Grafana"),
    ]
    nodes = "".join(
        f'<rect class="node" x="{x}" y="100" width="135" height="76" rx="10"/>'
        f'<text x="{x + 67}" y="145" text-anchor="middle" font-size="16">{label}</text>'
        for x, label in architecture_nodes
    )
    lines = "".join(
        f'<line x1="{x + 135}" y1="138" x2="{x + 158}" y2="138" '
        'stroke="#1A8C8C" stroke-width="3" marker-end="url(#arrow)"/>'
        for x, _ in architecture_nodes[:-1]
    )
    architecture_svg = "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="300" '
            'viewBox="0 0 1200 300">',
            style,
            marker,
            '<text x="30" y="48" font-size="28" font-weight="bold">'
            "Shortly service and observability</text>",
            lines,
            nodes,
            '<text x="400" y="235" font-size="16">'
            "HPA 2–5 · PDB minAvailable 1 · ServiceMonitor · Redis persistent volume</text>",
            "</svg>",
        ]
    )
    pipeline_steps = [
        "Push",
        "Lint + test",
        "Build + scan",
        "GHCR",
        "Preflight",
        "Digest",
        "Deploy",
        "Verify",
    ]
    pipeline_nodes = "".join(
        f'<rect class="{"node" if i < 4 else "local"}" '
        f'x="{20 + i * 145}" y="120" width="122" height="72" rx="9"/>'
        f'<text x="{81 + i * 145}" y="162" text-anchor="middle" '
        f'font-size="15">{label}</text>'
        for i, label in enumerate(pipeline_steps)
    )
    pipeline_lines = "".join(
        f'<line x1="{142 + i * 145}" y1="156" x2="{163 + i * 145}" y2="156" '
        'stroke="#1A8C8C" stroke-width="3" marker-end="url(#arrow)"/>'
        for i in range(len(pipeline_steps) - 1)
    )
    pipeline_svg = "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="300" '
            'viewBox="0 0 1200 300">',
            style,
            marker,
            '<text x="25" y="52" font-size="28" font-weight="bold">'
            "Hosted checks then guarded local deployment</text>",
            pipeline_lines,
            pipeline_nodes,
            '<text x="735" y="240" font-size="16">'
            "Pass → deployed · fail → automatic undo; job remains red</text>",
            "</svg>",
        ]
    )
    (assets / "architecture.svg").write_text(architecture_svg, encoding="utf-8")
    (assets / "pipeline.svg").write_text(pipeline_svg, encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    write_diagram_assets()
    presentation = Presentation()
    presentation.slide_width = Inches(SLIDE_W)
    presentation.slide_height = Inches(SLIDE_H)
    presentation.core_properties.title = "Shortly DevOps — CA2 report"
    presentation.core_properties.subject = "Architecture, pipeline, challenges and lessons learned"
    presentation.core_properties.author = "<Group members>"
    slide_builders = [
        slide_architecture,
        slide_pipeline,
        slide_evidence,
        slide_challenges,
        slide_lessons,
    ]
    for builder in slide_builders:
        builder(presentation)
    pptx_path = OUT / "shortly-devops-slides.pptx"
    presentation.save(pptx_path)
    print("SLIDE TITLES:")
    for index, slide in enumerate(presentation.slides, 1):
        title = next(
            (
                shape.text
                for shape in slide.shapes
                if getattr(shape, "has_text_frame", False) and shape.top < Inches(1)
            ),
            "",
        )
        print(f"{index}. {title}")
    print(f"Slide count: {len(presentation.slides)}")
    print(f"Wrote {pptx_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
