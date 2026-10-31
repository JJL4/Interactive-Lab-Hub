import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import textwrap
import time

import cv2
import mediapipe as mp
import requests
from ultralytics import YOLO

LOG_PATH = Path("mug_night_log.jsonl")
SNAP_DIR = Path("mug_snaps")
MODEL = "qwen3.5:0.8b"


def now_string():
    return dt.datetime.now().isoformat(timespec="seconds")


def log_event(fp, **items):
    entry = {"t": now_string(), **items}
    fp.write(json.dumps(entry) + "\n")
    fp.flush()
    print(entry, flush=True)


def is_quiet_coyote(hand_landmarks):
    """Index and pinky extended; middle and ring folded, upright hand."""
    p = hand_landmarks.landmark
    # Landmark vertical relationships work for an upright hand facing camera.
    index_up = p[8].y < p[6].y - 0.035
    pinky_up = p[20].y < p[18].y - 0.025
    middle_down = p[12].y > p[10].y - 0.015
    ring_down = p[16].y > p[14].y - 0.015
    # Prevent the index and pinky from being barely raised.
    spread = math.hypot(p[8].x - p[20].x, p[8].y - p[20].y)
    return index_up and pinky_up and middle_down and ring_down and spread > 0.14


class MiniPiTFT:
    """1.14-inch ST7789: live status at 1 Hz plus paged Qwen results."""

    def __init__(self, enabled=True):
        self.disp = None
        self.error = None
        self.writes = 0
        self.last_error_print = 0.0
        if not enabled:
            print("Mini PiTFT disabled by --no-display", flush=True)
            return
        try:
            import board
            import digitalio
            from adafruit_rgb_display import st7789
            from PIL import Image, ImageDraw, ImageFont
            self.Image, self.ImageDraw, self.ImageFont = Image, ImageDraw, ImageFont
            self.cs = digitalio.DigitalInOut(board.D5)
            self.dc = digitalio.DigitalInOut(board.D25)
            self.backlight = digitalio.DigitalInOut(board.D22)
            self.backlight.switch_to_output(value=True)
            self.disp = st7789.ST7789(
                board.SPI(), cs=self.cs, dc=self.dc, rst=None,
                baudrate=64000000, width=135, height=240,
                x_offset=53, y_offset=40,
            )
            self.title_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
            self.body_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
            self.small_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
            print("Mini PiTFT initialized (240x135 landscape)", flush=True)
        except Exception as exc:
            self.error = str(exc)
            self.disp = None
            print(f"Mini PiTFT initialization failed: {exc}", flush=True)
            print("Make sure adafruit-blinka and adafruit-circuitpython-rgb-display "
                  "are installed in this venv and SPI is enabled.", flush=True)

    def _send(self, image):
        if self.disp is None:
            return False
        try:
            # 240x135 PIL canvas rotated to match physical 135x240 ST7789.
            self.disp.image(image, 90)
            self.writes += 1
            return True
        except Exception as exc:
            self.error = str(exc)
            t = time.monotonic()
            if t - self.last_error_print >= 10.0:
                print(f"Mini PiTFT draw failed: {exc}", flush=True)
                self.last_error_print = t
            return False

    def _canvas(self, title, color=(255, 210, 90)):
        im = self.Image.new("RGB", (240, 135), (8, 14, 27))
        draw = self.ImageDraw.Draw(im)
        draw.text((7, 5), title[:23], font=self.title_font, fill=color)
        draw.line((7, 29, 233, 29), fill=(96, 112, 130), width=1)
        return im, draw

    def page(self, title, lines):
        if self.disp is None:
            return False
        image, draw = self._canvas(title)
        for i, line in enumerate(lines[:5]):
            draw.text((8, 34 + 18*i), str(line)[:31], font=self.body_font,
                      fill=(244, 245, 248))
        return self._send(image)

    def live(self, state, objects, last_scan, elapsed, gesture, held_since):
        """Refresh one time per second, even if no YOLO reading changes."""
        if self.disp is None:
            return False
        status = {"idle": "WAITING", "monitoring": "MONITORING", "report": "REPORT"}.get(state, state.upper())
        status_color = (120, 225, 255) if state == "idle" else (100, 245, 135)
        image, draw = self._canvas("MIDNIGHT MUG")
        draw.text((9, 34), status, font=self.body_font, fill=status_color)
        cups = [o for o in objects if o["name"] == "cup"]
        if last_scan is None:
            mug_status = "NO SCAN YET"
            color = (235, 210, 130)
        elif cups:
            mug_status = f"CUP DETECTED ({len(cups)})"
            color = (105, 240, 120)
        else:
            mug_status = "CUP NOT SEEN"
            color = (255, 130, 115)
        draw.text((9, 53), mug_status, font=self.title_font, fill=color)
        names = list(dict.fromkeys(o["name"] for o in objects))
        objs = ", ".join(names[:4]) if names else "nothing"
        draw.text((9, 78), f"YOLO: {objs}"[:33], font=self.small_font, fill=(230, 230, 230))
        if last_scan is None:
            age = "scan pending"
        else:
            age = f"scan {max(0, int(time.monotonic()-last_scan))}s ago"
        draw.text((9, 94), f"{age}  |  {int(elapsed)}s elapsed"[:35],
                  font=self.small_font, fill=(180, 200, 220))
        if gesture:
            hold = max(0.0, time.monotonic() - held_since) if held_since is not None else 0.0
            bottom = f"QUIET COYOTE {min(2,hold):.1f}/2.0s"
        elif state == "idle":
            bottom = "Show Quiet Coyote to start"
        else:
            bottom = "Show Quiet Coyote to stop"
        draw.text((9, 113), bottom[:36], font=self.small_font, fill=(255, 210, 110))
        return self._send(image)

    def test(self):
        """Visible four-second self-test, no camera/YOLO needed."""
        if self.disp is None:
            return False
        for n in range(4):
            image, draw = self._canvas("DISPLAY TEST")
            draw.rectangle((8, 39, 231, 95), fill=[(140, 50, 50), (55, 135, 65),
                                                    (50, 85, 155), (140, 100, 45)][n])
            draw.text((18, 54), f"Frame {n+1} / 4", font=self.title_font,
                      fill=(255, 255, 255))
            if not self._send(image):
                return False
            time.sleep(1)
        return self.page("DISPLAY READY", ["Live status enabled", "1 update / second"])


def qwen_report(entries):
    """Let Qwen select a report from *verified* observations only.

    YOLO provides cup visibility, not mug motion or a tracked position.
    We construct two factual report choices and accept Qwen's output ONLY
    if it exactly matches one of them. Otherwise use the factual fallback.
    """
    readings = [e for e in entries if e.get("reading") in
                ("cup detected", "cup not detected")]
    if not readings:
        return "No mug observations were recorded."

    last = readings[-1]
    last_time = str(last.get("t", "unknown time"))[11:16] or "unknown time"
    status = last["reading"]
    changes = len(readings) - 1  # Entries are logged only on status changes.
    change_word = "change" if changes == 1 else "changes"

    if changes == 0 and status == "cup detected":
        choices = [
            f"Cup detected at {last_time}; no detection changes were logged.",
            f"Mug Watch: cup visible at {last_time}; no detection changes logged.",
        ]
    elif changes == 0:
        choices = [
            f"Cup not detected at {last_time}. Its location is unknown.",
            f"Mug Watch: no cup seen at {last_time}; its location is unknown.",
        ]
    else:
        choices = [
            f"There were {changes} detection {change_word}; last status at {last_time}: {status}.",
            f"Mug Watch: {changes} detection {change_word}. Last logged at {last_time}: {status}.",
        ]

    prompt = (
        "Choose ONE of the following two factual mug status reports. "
        "Respond with EXACTLY one option, verbatim; no other text. "
        "The detector measures cup visibility only. It cannot tell whether "
        "the mug moved, changed position, was taken, or who touched it.\n\n"
        "OPTION 1: " + choices[0] + "\n"
        "OPTION 2: " + choices[1] + "\n"
    )
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": MODEL, "prompt": prompt, "think": False,
                  "stream": False, "options": {"temperature": 0,
                                               "num_predict": 110}},
            timeout=600,
        )
        response.raise_for_status()
        result = response.json().get("response", "").strip()
        if result in choices:
            return result
        print("Qwen output was not one of the verified reports; "
              "using factual fallback.", flush=True)
    except requests.RequestException as exc:
        print(f"Qwen unavailable ({exc}); using factual fallback.", flush=True)
    return choices[0]



def cv_preview_available():
    """Avoid OpenCV HighGUI aborts in SSH/headless environments."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False, "no desktop display found (open a VNC desktop)"
    gui_line = next((line.strip() for line in cv2.getBuildInformation().splitlines()
                     if line.strip().startswith("GUI:")), "")
    if "NONE" in gui_line.upper():
        return False, "OpenCV was built without window/GUI support"
    return True, ""


def extract_objects(prediction):
    """Read all recognized YOLO objects; cup is the one that gets logged."""
    objects = []
    for box in prediction.boxes:
        cls = int(box.cls[0].item())
        label = str(prediction.names[cls])
        objects.append({
            "name": label,
            "confidence": float(box.conf[0].item()),
            "xyxy": tuple(int(round(v)) for v in box.xyxy[0].cpu().tolist()),
        })
    return objects


def hud_frame(frame, state, objects, last_scan, gesture, held_since,
              preview_interval, interval):
    """A live camera view with sampled YOLO detections and gesture state."""
    img = frame.copy()
    height, width = img.shape[:2]
    for obj in objects:
        x1, y1, x2, y2 = obj["xyxy"]
        x1, x2 = max(0, x1), min(width - 1, x2)
        y1, y2 = max(0, y1), min(height - 1, y2)
        cup = obj["name"] == "cup"
        color = (75, 230, 95) if cup else (250, 185, 65)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f'{obj["name"]} {obj["confidence"]:.0%}'
        text_w, text_h = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)[0]
        tag_y = max(19, y1)
        cv2.rectangle(img, (x1, tag_y - text_h - 8),
                      (min(width - 1, x1 + text_w + 8), tag_y + 3), color, -1)
        cv2.putText(img, label, (x1 + 4, tag_y - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (15, 20, 20), 1, cv2.LINE_AA)

    shade = img.copy()
    cv2.rectangle(shade, (0, 0), (width, 126), (15, 18, 22), -1)
    cv2.rectangle(shade, (0, height - 39), (width, height), (15, 18, 22), -1)
    img = cv2.addWeighted(shade, 0.72, img, 0.28, 0)
    # Repaint labels on top of shade; bounding boxes remain visible beneath HUD.
    mode = {"idle": "WAITING FOR GESTURE", "monitoring": "MONITORING",
            "report": "REPORT"}.get(state, state.upper())
    mode_color = (75, 230, 95) if state == "monitoring" else (90, 220, 245)
    cv2.putText(img, f"MIDNIGHT MUG MYSTERY   [{mode}]", (12, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.59, mode_color, 2, cv2.LINE_AA)

    cup_objects = [o for o in objects if o["name"] == "cup"]
    if last_scan is None:
        status = "Cup: waiting for first YOLO scan"
        scan = "Last scan: not yet"
    else:
        status = (f"Cup: DETECTED ({len(cup_objects)})" if cup_objects
                  else "Cup: NOT DETECTED")
        scan = f"Last YOLO scan: {max(0, time.monotonic() - last_scan):.1f}s ago"
    cv2.putText(img, status, (12, 49), cv2.FONT_HERSHEY_SIMPLEX, 0.54,
                (90, 230, 105) if cup_objects else (80, 175, 250), 2, cv2.LINE_AA)
    names = []
    for obj in objects:
        if obj["name"] not in names:
            names.append(obj["name"])
    objline = "YOLO sees: " + (", ".join(names[:7]) if names else "nothing")
    if len(objline) > 74:
        objline = objline[:71] + "..."
    cv2.putText(img, objline, (12, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                (250, 250, 250), 1, cv2.LINE_AA)
    if gesture and held_since is not None:
        gesture_label = f"Quiet Coyote: HOLD {min(2.0, time.monotonic()-held_since):.1f}/2.0s"
    elif gesture:
        gesture_label = "Quiet Coyote: gesture seen (release to re-arm)"
    else:
        gesture_label = "Quiet Coyote: not detected"
    cv2.putText(img, gesture_label, (12, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (105, 235, 235) if gesture else (205, 205, 205), 1, cv2.LINE_AA)
    cv2.putText(img, scan, (12, 116), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (205, 205, 205), 1, cv2.LINE_AA)
    cv2.putText(img, f"YOLO ~{preview_interval:g}s | Log ~{interval:g}s | Q: finish/quit",
                (12, height - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                (240, 240, 240), 1, cv2.LINE_AA)
    return img


def report_frame(report, width=640, height=480):
    img = __import__("numpy").full((height, width, 3), (20, 25, 30), dtype="uint8")
    cv2.putText(img, "MORNING MUG REPORT", (25, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, (75, 230, 95), 2, cv2.LINE_AA)
    for i, line in enumerate(textwrap.wrap(report, 55)[:9]):
        cv2.putText(img, line, (25, 110 + i * 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 235, 235), 1,
                    cv2.LINE_AA)
    cv2.putText(img, "Press Q to exit", (25, height - 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 185, 220), 1, cv2.LINE_AA)
    return img


def main():
    parser = argparse.ArgumentParser(
        description="Mug monitor with a live YOLO webcam HUD and Quiet Coyote gestures")
    parser.add_argument("--interval", type=float, default=15.0,
                        help="Seconds between logged mug checks (default: 15)")
    parser.add_argument("--preview-interval", type=float, default=2.0,
                        help="Seconds between YOLO updates in the live webcam HUD (default: 2)")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--conf", type=float, default=0.25,
                        help="Minimum YOLO object confidence (default: 0.25)")
    parser.add_argument("--no-preview", "--headless", action="store_true",
                        help="Do not open a webcam window (useful over SSH/at night)")
    parser.add_argument("--no-display", action="store_true",
                        help="Disable the Mini PiTFT, but keep the webcam HUD")
    parser.add_argument("--test-display", action="store_true",
                        help="Test the Mini PiTFT without opening webcam or loading AI")
    parser.add_argument("--demo-seconds", type=float, default=0,
                        help="Automatically start/stop after N seconds for a test")
    args = parser.parse_args()
    if args.interval <= 0 or args.preview_interval <= 0:
        parser.error("--interval and --preview-interval must be positive")
    if not (0 < args.conf <= 1):
        parser.error("--conf must be between 0 and 1")
    if args.demo_seconds < 0:
        parser.error("--demo-seconds cannot be negative")

    preview = not args.no_preview
    if preview:
        available, reason = cv_preview_available()
        if not available:
            print(f"Webcam preview disabled: {reason}. Run from a VNC desktop to see it.",
                  flush=True)
            preview = False

    if args.test_display:
        screen = MiniPiTFT(enabled=True)
        if screen.disp is None:
            raise SystemExit("PiTFT did not initialize. See the error above.")
        if not screen.test():
            raise SystemExit("PiTFT initialized but could not draw. See error above.")
        print(f"PiTFT self-test passed: {screen.writes} successful frames", flush=True)
        return

    print("Loading YOLO NCNN model...", flush=True)
    model = YOLO("yolo26n_ncnn_model")
    print("Starting MediaPipe...", flush=True)
    hands = mp.solutions.hands.Hands(
        static_image_mode=False, max_num_hands=1, model_complexity=0,
        min_detection_confidence=0.6, min_tracking_confidence=0.6,
    )
    screen = MiniPiTFT(enabled=not args.no_display)
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        raise SystemExit("Webcam cannot open. Stop overnight.py or any other camera program.")

    SNAP_DIR.mkdir(exist_ok=True)
    state = "idle"
    log = None
    held_since = None
    released_since = None
    armed = True
    next_check = 0.0
    next_preview_scan = 0.0
    last_scan = None
    objects = []
    first_check = None
    last_reading = None
    entries = []
    report = ""
    report_pages = []
    report_page_i = -1
    next_page = 0.0
    next_tft_tick = 0.0
    window = "Midnight Mug Mystery - Live Webcam + YOLO"

    def start_monitoring():
        nonlocal state, log, next_check, first_check, last_reading, entries
        log = LOG_PATH.open("w", encoding="utf-8")
        log_event(log, event="monitoring_started")
        entries = []
        first_check = time.monotonic()
        next_check = first_check + 3.0  # Give user time to move their hand away.
        last_reading = None
        state = "monitoring"
        screen.page("MUG WATCH", ["Monitoring started", "Watching for cups", "Show gesture to stop"])
        print("Mug Watch started. Show Quiet Coyote again to finish.", flush=True)

    def finish_monitoring():
        nonlocal state, log, report, report_pages, next_page, report_page_i
        if state != "monitoring":
            return
        state = "report"
        if log is not None:
            log_event(log, event="monitoring_stopped")
            log.close()
            log = None
        screen.page("MUG WATCH", ["Monitoring stopped", "Qwen is thinking..."])
        print("Monitoring stopped. Asking Qwen...", flush=True)
        try:
            report = qwen_report(entries)
        except Exception as exc:
            report = f"Qwen unavailable: {exc}"
        print("\nMORNING REPORT:\n" + report, flush=True)
        lines = textwrap.wrap(report, width=27, break_long_words=False) or ["No report"]
        report_pages = [lines[i:i + 5] for i in range(0, len(lines), 5)]
        report_page_i = -1
        next_page = 0.0

    screen.page("MUG WATCH", ["Waiting for gesture", "Quiet Coyote x 2 s", "Mug on desk first"])
    print("Waiting for Quiet Coyote (hold ~2 seconds). Ctrl-C to exit.", flush=True)
    if preview:
        print("Live webcam HUD enabled. Yellow boxes=other objects; green=cups. Press Q to quit.",
              flush=True)
    if args.demo_seconds:
        start_monitoring()

    try:
        while True:
            if state == "report":
                if time.monotonic() >= next_page:
                    report_page_i = (report_page_i + 1) % len(report_pages)
                    screen.page("MORNING REPORT", report_pages[report_page_i])
                    next_page = time.monotonic() + 5.0
                if preview:
                    cv2.imshow(window, report_frame(report))
                    if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                        break
                elif args.demo_seconds:
                    break
                time.sleep(0.2)
                continue

            ok, frame = cap.read()
            if not ok:
                print("Camera frame unavailable; retrying", flush=True)
                time.sleep(0.4)
                continue
            t = time.monotonic()
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)
            gesture = any(is_quiet_coyote(h) for h in
                          (result.multi_hand_landmarks or []))

            # The Mini PiTFT refreshes once per second even if cup detection is unchanged.
            # In idle mode elapsed=0; during monitoring elapsed is seconds since start.
            if t >= next_tft_tick:
                elapsed = (t - first_check) if state == "monitoring" and first_check else 0.0
                screen.live(state, objects, last_scan, elapsed, gesture, held_since)
                next_tft_tick = t + 1.0

            if gesture:
                released_since = None
                if armed:
                    if held_since is None:
                        held_since = t
                    elif t - held_since >= 2.0:
                        armed = False
                        held_since = None
                        if state == "idle":
                            start_monitoring()
                        elif state == "monitoring":
                            finish_monitoring()
                        # The next iteration will switch to the report view as needed.
                        continue
            else:
                held_since = None
                if released_since is None:
                    released_since = t
                elif t - released_since >= 1.0:
                    armed = True

            if state == "monitoring" and args.demo_seconds and t - first_check >= args.demo_seconds:
                finish_monitoring()
                continue

            # Webcam frames are live. YOLO runs periodically, not on every video frame,
            # so its bounding boxes/HUD clearly show the age of the latest detection.
            due_log = state == "monitoring" and t >= next_check
            due_preview = preview and t >= next_preview_scan
            if due_log or due_preview:
                # In preview, show *all* classes; only COCO "cup" is logged.
                # In headless mode limit processing to cups to reduce overhead.
                prediction = model.predict(
                    frame, imgsz=640, conf=args.conf,
                    classes=None if preview else [41], verbose=False,
                )[0]
                objects = extract_objects(prediction)
                last_scan = time.monotonic()
                next_preview_scan = last_scan + args.preview_interval

                if due_log:
                    detected = any(obj["name"] == "cup" for obj in objects)
                    reading = "cup detected" if detected else "cup not detected"
                    print(f"{now_string()} {reading}", flush=True)
                    if reading != last_reading:
                        log_event(log, reading=reading)
                        entries.append({"t": now_string(), "reading": reading})
                        cv2.imwrite(str(
                            SNAP_DIR / f"mug-{dt.datetime.now():%Y%m%d-%H%M%S}.jpg"),
                            prediction.plot())
                        screen.page("MUG WATCH", ["Monitoring active", reading,
                                                  "Quiet Coyote to stop"])
                        last_reading = reading
                    next_check = time.monotonic() + args.interval

            if preview:
                cv2.imshow(window, hud_frame(
                    frame, state, objects, last_scan, gesture, held_since,
                    args.preview_interval, args.interval))
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    if state == "monitoring":
                        finish_monitoring()
                    else:
                        break
            time.sleep(0.06 if preview else 0.1)

    except KeyboardInterrupt:
        if state == "monitoring":
            finish_monitoring()
            if screen.disp is not None:
                lines = textwrap.wrap(report, width=27, break_long_words=False)
                screen.page("MORNING REPORT", lines[:5])
        print("\nExiting.", flush=True)
    finally:
        if log is not None:
            log.close()
        cap.release()
        hands.close()
        if preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
