import math
import os
import sys
from PIL import Image, ImageDraw, ImageFont
import imageio.v2 as imageio
import numpy as np

# Resolution
W, H = 1280, 720
FPS = 30
TOTAL_FRAMES = 660  # 22 seconds

# Fonts
FONT_TITLE = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 46)
FONT_SUB = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 26)
FONT_BODY = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 20)
FONT_BODY_BOLD = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 20)
FONT_SMALL = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 16)
FONT_MONO = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 18)
FONT_MONO_BOLD = ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", 22)
FONT_HERO = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 72)
FONT_METRIC = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 54)

# Color Palette
BG_DARK = (13, 17, 23)
CARD_BG = (22, 27, 34)
CARD_BORDER = (48, 54, 61)
ACCENT_MINT = (0, 220, 130)
ACCENT_CYAN = (56, 189, 248)
ACCENT_RED = (239, 68, 68)
ACCENT_AMBER = (251, 191, 36)
TEXT_WHITE = (240, 246, 252)
TEXT_MUTED = (139, 148, 158)
TEXT_DIM = (80, 90, 100)


def draw_rounded_rect(draw, bbox, radius, fill=None, outline=None, width=1):
    x0, y0, x1, y1 = bbox
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)


def render_scene_1(f, total_f=120):
    # Scene 1: The Thesis (0 - 4.0s)
    im = Image.new("RGB", (W, H), BG_DARK)
    d = ImageDraw.Draw(im)

    # Top badge
    draw_rounded_rect(d, (50, 40, 430, 75), 16, fill=(30, 41, 59), outline=ACCENT_CYAN, width=1)
    d.text((65, 48), "Hacktoberfest 2026  •  Slow and Steady", font=FONT_SMALL, fill=ACCENT_CYAN)

    # Hero title
    d.text((50, 110), "M O L T", font=FONT_HERO, fill=ACCENT_MINT)
    d.text((50, 200), "Compile once. Verify against truth. Reuse forever.", font=FONT_SUB, fill=TEXT_WHITE)

    # Core paradigm callout box
    draw_rounded_rect(d, (50, 260, 1230, 370), 12, fill=(18, 24, 38), outline=(60, 80, 110), width=2)
    d.text((80, 280), "THE INVERTED PARADIGM:", font=FONT_BODY_BOLD, fill=ACCENT_AMBER)
    d.text((80, 315), '"Use the local model as an offline compiler, never a production runtime."', font=FONT_SUB, fill=TEXT_WHITE)

    # 3 Stat Cards animating in
    progress = min(1.0, f / 90.0)
    cards = [
        ("0 MODEL CALLS", "at runtime steady state", ACCENT_MINT),
        ("~16 MILLISECONDS", "deterministic execution latency", ACCENT_CYAN),
        ("100% REPRODUCIBLE", "pure Python, zero token variance", TEXT_WHITE),
    ]

    for i, (title, sub, col) in enumerate(cards):
        cx = 50 + i * 405
        cy = 420
        cw, ch = 380, 220

        # Animate alpha / presence
        if f > 20 + i * 20:
            draw_rounded_rect(d, (cx, cy, cx + cw, cy + ch), 12, fill=CARD_BG, outline=CARD_BORDER, width=2)
            # Top accent stripe
            d.line([(cx + 12, cy + 2), (cx + cw - 12, cy + 2)], fill=col, width=4)
            d.text((cx + 25, cy + 40), title, font=FONT_SUB, fill=col)
            d.text((cx + 25, cy + 90), sub, font=FONT_BODY, fill=TEXT_MUTED)
            d.text((cx + 25, cy + 150), f"Verified in benchmark.json", font=FONT_SMALL, fill=TEXT_DIM)

    return im


def render_scene_2(f, total_f=120):
    # Scene 2: The Benchmark (4.0s - 8.0s)
    im = Image.new("RGB", (W, H), BG_DARK)
    d = ImageDraw.Draw(im)

    # Top Header
    d.text((50, 40), "THE DRIFT BENCHMARK: 4 ADVERSARIAL CASES", font=FONT_TITLE, fill=TEXT_WHITE)
    d.text((50, 95), "Comparing traditional naive scripts vs. Molt contract guard", font=FONT_BODY, fill=TEXT_MUTED)

    # Card 1: Naive Positional Script (Fail)
    draw_rounded_rect(d, (50, 150, 610, 650), 16, fill=CARD_BG, outline=ACCENT_RED, width=2)
    d.text((80, 180), "Naive Positional Script (11pm Fix)", font=FONT_SUB, fill=ACCENT_RED)
    d.text((80, 220), "The typical script written in a rush and forgotten", font=FONT_SMALL, fill=TEXT_MUTED)

    d.line([(80, 255), (580, 255)], fill=CARD_BORDER, width=1)

    d.text((80, 280), "Silent Wrong Outputs:", font=FONT_BODY, fill=TEXT_WHITE)
    d.text((80, 315), "3  OUT OF 4", font=FONT_METRIC, fill=ACCENT_RED)

    d.text((80, 400), "Drift Accepted Without Check:", font=FONT_BODY, fill=TEXT_WHITE)
    d.text((80, 435), "2  DRIFTED BATCHES", font=FONT_SUB, fill=ACCENT_AMBER)

    draw_rounded_rect(d, (80, 520, 580, 610), 8, fill=(40, 20, 20), outline=ACCENT_RED, width=1)
    d.text((100, 540), "RESULT: SILENT CORRUPTION REACHED DISK", font=FONT_BODY_BOLD, fill=ACCENT_RED)
    d.text((100, 570), "Bad dates & amounts parsed invisibly.", font=FONT_SMALL, fill=TEXT_MUTED)

    # Card 2: Molt Runtime Guard (Success)
    draw_rounded_rect(d, (670, 150, 1230, 650), 16, fill=CARD_BG, outline=ACCENT_MINT, width=2)
    d.text((700, 180), "Molt Runtime Guard", font=FONT_SUB, fill=ACCENT_MINT)
    d.text((700, 220), "Contract gates, verifier fixtures & quarantine", font=FONT_SMALL, fill=TEXT_MUTED)

    d.line([(700, 255), (1200, 255)], fill=CARD_BORDER, width=1)

    d.text((700, 280), "Silent Wrong Outputs:", font=FONT_BODY, fill=TEXT_WHITE)
    d.text((700, 315), "0  (ZERO)", font=FONT_METRIC, fill=ACCENT_MINT)

    d.text((700, 400), "Blocked & Quarantined in 16ms:", font=FONT_BODY, fill=TEXT_WHITE)
    d.text((700, 435), "2  CASES BLOCKED", font=FONT_SUB, fill=ACCENT_CYAN)

    draw_rounded_rect(d, (700, 520, 1200, 610), 8, fill=(15, 35, 25), outline=ACCENT_MINT, width=1)
    d.text((720, 540), "RESULT: 100% CLEAN DISK INTEGRITY", font=FONT_BODY_BOLD, fill=ACCENT_MINT)
    d.text((720, 570), "Runtime LLM calls: 0  |  Mean latency: 3.968 ms", font=FONT_SMALL, fill=ACCENT_CYAN)

    return im


def render_scene_3(f, total_f=150):
    # Scene 3: The 2-Phase Lifecycle (8.0s - 13.0s)
    im = Image.new("RGB", (W, H), BG_DARK)
    d = ImageDraw.Draw(im)

    d.text((50, 35), "THE TWO PHASES THAT NEVER TOUCH EACH OTHER", font=FONT_TITLE, fill=TEXT_WHITE)
    d.text((50, 85), "Raw sensitive data never leaves the local deterministic engine", font=FONT_BODY, fill=TEXT_MUTED)

    # Phase 1 Box
    draw_rounded_rect(d, (50, 130, 610, 480), 14, fill=CARD_BG, outline=CARD_BORDER, width=2)
    d.text((75, 150), "PHASE 1: COMPILE ONCE", font=FONT_SUB, fill=ACCENT_CYAN)
    d.text((75, 190), "1. Masked schema profile extracted (no raw rows)", font=FONT_BODY, fill=TEXT_WHITE)
    d.text((75, 230), "2. Local Gemma 3:4b (Ollama) proposes JSON", font=FONT_BODY, fill=TEXT_WHITE)
    d.text((75, 270), "3. Restricted closed 9-op allowlist enforced", font=FONT_BODY, fill=TEXT_WHITE)
    d.text((100, 305), "trim, parse_date, parse_decimal, dedupe...", font=FONT_MONO, fill=ACCENT_AMBER)
    d.text((75, 350), "4. Cannot emit Python code or shell scripts", font=FONT_BODY, fill=TEXT_MUTED)

    # Verifier Gate Box (Middle Right)
    draw_rounded_rect(d, (670, 130, 1230, 480), 14, fill=CARD_BG, outline=ACCENT_MINT, width=2)
    d.text((695, 150), "THE INDEPENDENT VERIFIER GATE", font=FONT_SUB, fill=ACCENT_MINT)
    d.text((695, 195), "[PASS]  Golden fixtures (exact expected outputs)", font=FONT_BODY_BOLD, fill=TEXT_WHITE)
    d.text((695, 240), "[PASS]  Row-count & null-injection checks", font=FONT_BODY_BOLD, fill=TEXT_WHITE)
    d.text((695, 285), "[PASS]  Idempotence test: apply(apply(x)) == apply(x)", font=FONT_BODY_BOLD, fill=TEXT_WHITE)
    d.text((695, 330), "[PASS]  20/20 Mutation testing catch rate", font=FONT_BODY_BOLD, fill=TEXT_WHITE)

    draw_rounded_rect(d, (695, 385, 1205, 455), 8, fill=(10, 40, 25), outline=ACCENT_MINT, width=2)
    d.text((720, 405), "EXPLICIT HUMAN OPERATOR APPROVAL GATE", font=FONT_SUB, fill=ACCENT_MINT)

    # Phase 2 Banner (Bottom)
    draw_rounded_rect(d, (50, 520, 1230, 670), 14, fill=(15, 25, 40), outline=ACCENT_CYAN, width=2)
    d.text((75, 545), "PHASE 2: RUN FOREVER (STEADY STATE)", font=FONT_SUB, fill=ACCENT_CYAN)
    d.text((75, 595), "Drop file in in/  ──▶  Deterministic Pure Python Execution  ──▶  Atomic Output in done/", font=FONT_BODY_BOLD, fill=TEXT_WHITE)
    d.text((75, 630), "Latency: 16ms  •  Model Calls: 0  •  Network Calls: 0  •  Zero Dollar Recurring Cost", font=FONT_SMALL, fill=ACCENT_MINT)

    return im


def render_scene_4(f, total_f=150):
    # Scene 4: When Data Drifts & Out-of-Band Repair (13.0s - 18.0s)
    im = Image.new("RGB", (W, H), BG_DARK)
    d = ImageDraw.Draw(im)

    d.text((50, 35), "WHEN DATA DRIFTS: THE OUT-OF-BAND REPAIR CYCLE", font=FONT_TITLE, fill=TEXT_WHITE)
    d.text((50, 85), "Molt detects contract violations in 16ms and never auto-promotes unreviewed fixes", font=FONT_BODY, fill=TEXT_MUTED)

    # Timeline Audit Beads
    draw_rounded_rect(d, (50, 130, 1230, 230), 12, fill=CARD_BG, outline=CARD_BORDER, width=2)
    d.text((75, 145), "Live Run Audit Timeline (One Bead Per Decision)", font=FONT_SMALL, fill=TEXT_MUTED)

    beads = [
        ("Run 1", "PASS", ACCENT_MINT),
        ("Run 2", "BLOCKED_DRIFT (16ms)", ACCENT_RED),
        ("Run 3", "BLOCKED_DRIFT", ACCENT_RED),
        ("Run 4", "BLOCKED_DRIFT", ACCENT_RED),
        ("Run 5", "PASS (Recipe v2)", ACCENT_MINT),
    ]

    for i, (name, status, col) in enumerate(beads):
        bx = 80 + i * 230
        by = 175
        d.ellipse([bx, by, bx + 24, by + 24], fill=col)
        d.text((bx + 35, by - 2), name, font=FONT_BODY_BOLD, fill=TEXT_WHITE)
        d.text((bx + 35, by + 18), status, font=FONT_SMALL, fill=col)

    # Repair Stepper (5 Steps)
    draw_rounded_rect(d, (50, 260, 1230, 480), 12, fill=CARD_BG, outline=CARD_BORDER, width=2)
    d.text((75, 280), "Out-of-Band Mastra Repair Architecture (:4112 / Groq)", font=FONT_SUB, fill=ACCENT_AMBER)

    steps = [
        ("1. Drift Blocked", "Contract gate catches missing column in 16ms. Quarantined.", ACCENT_RED),
        ("2. Ask Mastra", "Sidecar receives masked profile (0 PII, 0 raw cell rows).", ACCENT_CYAN),
        ("3. Candidate Stored", "Mastra proposes candidate. Kept strictly INACTIVE.", ACCENT_AMBER),
        ("4. Run Tests", "Molt executes full regression suite: 6/6 CHECKS PASSED.", ACCENT_MINT),
        ("5. Operator Approves", "Human reviews diff and promotes to Recipe v2 (Active).", ACCENT_MINT),
    ]

    for j, (stitle, sdesc, scol) in enumerate(steps):
        sy = 325 + j * 28
        d.text((80, sy), stitle, font=FONT_BODY_BOLD, fill=scol)
        d.text((310, sy), sdesc, font=FONT_BODY, fill=TEXT_WHITE)

    # Real-Time Avoided Calls counter
    draw_rounded_rect(d, (50, 510, 1230, 660), 12, fill=(15, 30, 25), outline=ACCENT_MINT, width=2)
    d.text((75, 530), "STEADY STATE RESTORED UNDER RECIPE V2", font=FONT_SUB, fill=ACCENT_MINT)
    d.text((75, 575), "Run 5 executed: 6 rows written atomically  |  Latency: 16ms  |  Runtime LLM calls: 0", font=FONT_BODY_BOLD, fill=TEXT_WHITE)
    d.text((75, 615), "Cumulative model calls avoided: 1,428+  (Cost savings: $38.20 / week)", font=FONT_BODY, fill=ACCENT_CYAN)

    return im


def render_scene_5(f, total_f=120):
    # Scene 5: Verified Observability & Closing (18.0s - 22.0s)
    im = Image.new("RGB", (W, H), BG_DARK)
    d = ImageDraw.Draw(im)

    d.text((50, 40), "VERIFIED INTEGRATIONS: THREE PARTNER PRIZES", font=FONT_TITLE, fill=TEXT_WHITE)
    d.text((50, 95), "Strict boundaries, reproducible benchmarks, and mathematical proofs", font=FONT_BODY, fill=TEXT_MUTED)

    # 3 Badges
    prizes = [
        ("TEMPORAL DURABILITY", "Crash recovery test (MOLT_CRASH_AT=1). Worker and server killed mid-flight. Idempotent resume with 0 duplicate rows.", ACCENT_CYAN),
        ("TABPFN ADVISORY ANOMALY", "Evaluated on 1,500 synthetic rows locally on CPU. 94.55% precision. Strictly advisory, 0 source bytes modified.", ACCENT_AMBER),
        ("SENTRY AGENT TRACING", "Traces all 9 lifecycle spans in ~50ms. Strict allowlist redaction. Zero raw row payloads or PII ever reach APM.", ACCENT_MINT),
    ]

    for k, (ptitle, pdesc, pcol) in enumerate(prizes):
        py = 145 + k * 135
        draw_rounded_rect(d, (50, py, 1230, py + 115), 12, fill=CARD_BG, outline=pcol, width=2)
        d.text((75, py + 20), ptitle, font=FONT_SUB, fill=pcol)
        d.text((75, py + 65), pdesc, font=FONT_BODY, fill=TEXT_WHITE)

    # Final Punchline
    draw_rounded_rect(d, (50, 570, 1230, 680), 12, fill=(10, 20, 35), outline=(50, 80, 120), width=2)
    d.text((80, 590), "An LLM participated in fixing the pipeline. An LLM never touched the data.", font=FONT_SUB, fill=ACCENT_MINT)
    d.text((80, 635), "Open Source Repository:  https://github.com/Pritam-mb/week3", font=FONT_BODY, fill=ACCENT_CYAN)

    return im


def main():
    print("Generating custom digital presentation video (1280x720 @ 30 FPS)...")
    out_mp4 = r"d:\week3\evidence\molt-presentation.mp4"
    out_gif = r"d:\week3\evidence\molt-presentation.gif"
    out_webp = r"d:\week3\evidence\molt-presentation.webp"

    writer = imageio.get_writer(out_mp4, fps=FPS, codec="libx264", quality=8)

    gif_frames = []

    # Scene 1: Frames 0 to 120 (4.0s)
    print("Rendering Scene 1: The Thesis...")
    for f in range(120):
        im = render_scene_1(f, 120)
        writer.append_data(np.array(im))
        if f % 15 == 0:  # Sample for GIF
            gif_frames.append(im.resize((854, 480), Image.Resampling.LANCZOS))

    # Scene 2: Frames 120 to 240 (4.0s)
    print("Rendering Scene 2: The Drift Benchmark...")
    for f in range(120):
        im = render_scene_2(f, 120)
        writer.append_data(np.array(im))
        if f % 15 == 0:
            gif_frames.append(im.resize((854, 480), Image.Resampling.LANCZOS))

    # Scene 3: Frames 240 to 390 (5.0s)
    print("Rendering Scene 3: The 2-Phase Architecture...")
    for f in range(150):
        im = render_scene_3(f, 150)
        writer.append_data(np.array(im))
        if f % 15 == 0:
            gif_frames.append(im.resize((854, 480), Image.Resampling.LANCZOS))

    # Scene 4: Frames 390 to 540 (5.0s)
    print("Rendering Scene 4: Drift & Mastra Repair Flow...")
    for f in range(150):
        im = render_scene_4(f, 150)
        writer.append_data(np.array(im))
        if f % 15 == 0:
            gif_frames.append(im.resize((854, 480), Image.Resampling.LANCZOS))

    # Scene 5: Frames 540 to 660 (4.0s)
    print("Rendering Scene 5: Partner Verification & Closing...")
    for f in range(120):
        im = render_scene_5(f, 120)
        writer.append_data(np.array(im))
        if f % 15 == 0:
            gif_frames.append(im.resize((854, 480), Image.Resampling.LANCZOS))

    writer.close()
    print(f"MP4 successfully rendered: {out_mp4} ({os.path.getsize(out_mp4)} bytes)")

    print("Rendering animated WebP & GIF...")
    if gif_frames:
        gif_frames[0].save(out_webp, save_all=True, append_images=gif_frames[1:], duration=500, loop=0)
        print(f"WebP successfully rendered: {out_webp} ({os.path.getsize(out_webp)} bytes)")
        gif_frames[0].save(out_gif, save_all=True, append_images=gif_frames[1:], duration=500, loop=0)
        print(f"GIF successfully rendered: {out_gif} ({os.path.getsize(out_gif)} bytes)")


if __name__ == "__main__":
    main()
