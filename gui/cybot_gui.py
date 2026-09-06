"""
/******************************************************************************
 * AI DISCLOSURE:
 * - Tool: [ChatGPT-5.5] by OpenAI
 * - Scope: Used to help write initial mapping functionality and build/drawing functions of the GUI layout. Also helped with overall structure.
 * - Human Intervention: Modified the generated code to fix many logical bugs, and make it actually human usable to make it better for our Drivers.
 *   GPT assistance here was used to help make save time, but it was heavily reviewed and refined by: David, Mumbina, Conner, and Carter to get this to
 *   an actually good state.
 *****************************************************************************/
"""

from __future__ import annotations

import math
import queue
import re
import socket
import threading
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Tuple


# ---------------------- easy settings to change ----------------------

NEAR_LIMIT_CM = 50.0
FAR_LIMIT_CM = 100.0
FRONT_FOCUS_DISPLAY_CM = 75.0  # 50 real cm is drawn 75% of the way out on the scan view
IGNORE_WIDTH_BELOW_CM = 1.0
PILLAR_MIN_WIDTH_CM = 1.0
PILLAR_MAX_WIDTH_CM = 5.0

# These are display sizes only. Change these if the drawing looks too big/small.
CYBOT_WIDTH_CM = 36.0
MAP_CYBOT_PIXEL_SCALE = 0.70
FRONT_CYBOT_PIXEL_SCALE = 1.00
FRONT_CYBOT_Y_OFFSET_PX = 0  # extra adjustment after aligning CyBot front edge with semicircle bottom edge
PILLAR_PIXEL_SCALE = 2.8
OBJECT_WIDTH_PIXEL_SCALE = 1.15
MIN_OBJECT_PIXEL_RADIUS = 4
MAX_OBJECT_PIXEL_RADIUS = 48
HIT_HOLE_DIAMETER_CM = 13.0
BOUNDARY_DIAMETER_CM = 5.0

# Map is a relative operator map. Start is unknown, so the GUI starts at center.
MAP_W_CM = 840.0
MAP_H_CM = 840.0
START_X_CM = MAP_W_CM / 2
START_Y_CM = MAP_H_CM / 2

# Socket sending style. Usually empty string works for UART command characters.
# If your CyBot only works with PuTTY-style Enter, change this to "\r\n".
SEND_AFTER_COMMAND = ""

# Testing only. Keep False for final demo unless your team wants to see heartbeat lines.
SHOW_HEARTBEAT_LINES = False


# ---------------------- data objects ----------------------

@dataclass
class ScanObject:
    angle: float
    distance: float
    width: float
    scan_id: int
    world_x: Optional[float] = None
    world_y: Optional[float] = None

    def valid(self) -> bool:
        return self.width >= IGNORE_WIDTH_BELOW_CM

    def near(self) -> bool:
        return self.distance <= NEAR_LIMIT_CM

    def pillar_hint(self) -> bool:
        return PILLAR_MIN_WIDTH_CM <= self.width <= PILLAR_MAX_WIDTH_CM


@dataclass
class MapMark:
    x: float
    y: float
    kind: str
    label: str


@dataclass
class Robot:
    x: float = START_X_CM
    y: float = START_Y_CM
    heading: float = 0.0
    path: List[Tuple[float, float]] = field(default_factory=lambda: [(START_X_CM, START_Y_CM)])
    last_cmd: str = ""
    last_direction: int = 1
    connected: bool = False
    emergency_locked: bool = False


class CyBotGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CyBot Archaeology Survey GUI gui3")
        self.root.geometry("1580x960")
        self.root.minsize(1220, 780)
        self.root.configure(bg="#111827")

        self.sock: Optional[socket.socket] = None
        self.reader_thread: Optional[threading.Thread] = None
        self.stop_reader = threading.Event()
        self.rx_queue: queue.Queue[str] = queue.Queue()

        self.robot = Robot()
        self.scan_id = 0
        self.scan_objects: List[ScanObject] = []
        self.map_objects: List[ScanObject] = []
        self.map_marks: List[MapMark] = []
        self.sensor_values: Dict[str, str] = {}

        # Full-map-only page panning state.
        self.map_pan_x = 0.0
        self.map_pan_y = 0.0
        self.map_zoom = 1.0
        self.map_drag_start: Optional[Tuple[float, float]] = None

        self.host_var = tk.StringVar(value="192.168.1.1")
        self.port_var = tk.StringVar(value="288")
        self.status_var = tk.StringVar(value="Disconnected")
        self.big_message_var = tk.StringVar(value="Ready")
        self.pose_var = tk.StringVar(value="Path starts at unknown field position. GUI uses a relative start point.")
        self.sensor_var = tk.StringVar(value="Sensor status will show here after GUI_SENSOR lines.")
        self.command_var = tk.StringVar(value="")
        self.scan_summary_var = tk.StringVar(value="No scan yet")

        self.move_buttons: List[tk.Widget] = []
        self.scan_buttons: List[tk.Widget] = []

        self._setup_style()
        self._build_gui()
        self._bind_keys()
        self._draw_everything()
        self.root.after(40, self._poll_rx)
        self.root.after(300, self._redraw_timer)

    # ---------------------- GUI setup ----------------------

    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Dark.TFrame", background="#111827")
        style.configure("Card.TFrame", background="#1f2937")
        style.configure("Paper.TFrame", background="#f3f1df")
        style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=5)
        style.configure("Small.TButton", font=("Segoe UI", 8, "bold"), padding=4)
        style.configure("Title.TLabel", background="#1f2937", foreground="#f9fafb", font=("Segoe UI", 12, "bold"))
        style.configure("Text.TLabel", background="#1f2937", foreground="#e5e7eb", font=("Segoe UI", 10))
        style.configure("Paper.TLabel", background="#f3f1df", foreground="#111827", font=("Segoe UI", 10))
        style.configure("Good.TLabel", background="#064e3b", foreground="#ecfdf5", font=("Segoe UI", 18, "bold"))
        style.configure("Bad.TLabel", background="#7f1d1d", foreground="#fee2e2", font=("Segoe UI", 18, "bold"))
        style.configure("Warn.TLabel", background="#581c87", foreground="#f5d0fe", font=("Segoe UI", 18, "bold"))

    def _build_gui(self) -> None:
        top = ttk.Frame(self.root, style="Dark.TFrame", padding=8)
        top.pack(fill="x")
        tk.Label(top, text="CYBOT ARCHAEOLOGY SURVEY", bg="#111827", fg="#f9fafb", font=("Segoe UI", 16, "bold")).pack(side="left", padx=(0, 18))
        tk.Label(top, text="IP", bg="#111827", fg="#cbd5e1").pack(side="left")
        ttk.Entry(top, textvariable=self.host_var, width=15).pack(side="left", padx=4)
        tk.Label(top, text="Port", bg="#111827", fg="#cbd5e1").pack(side="left")
        ttk.Entry(top, textvariable=self.port_var, width=6).pack(side="left", padx=4)
        ttk.Button(top, text="Use Mock", command=self._use_mock).pack(side="left", padx=3)
        ttk.Button(top, text="Connect", command=self._connect).pack(side="left", padx=3)
        ttk.Button(top, text="Disconnect", command=self._disconnect).pack(side="left", padx=3)
        ttk.Button(top, text="Quick Demo", command=self._quick_demo).pack(side="left", padx=12)
        tk.Label(top, textvariable=self.status_var, bg="#111827", fg="#93c5fd", font=("Segoe UI", 11, "bold")).pack(side="right")

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.main_page = ttk.Frame(self.tabs, style="Dark.TFrame")
        self.full_map_page = ttk.Frame(self.tabs, style="Dark.TFrame")
        self.tabs.add(self.main_page, text="Main operator view")
        self.tabs.add(self.full_map_page, text="Full map only")

        self._build_main_page()
        self._build_full_map_page()

    def _build_main_page(self) -> None:
        p = self.main_page
        p.columnconfigure(0, weight=7)
        p.columnconfigure(1, weight=3)
        p.rowconfigure(0, weight=7)
        p.rowconfigure(1, weight=3)

        # Main and biggest thing: front obstacle window.
        front_card = ttk.Frame(p, style="Card.TFrame", padding=8)
        front_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(6, 4))
        front_card.rowconfigure(0, weight=1)
        front_card.columnconfigure(0, weight=1)
        self.front_canvas = tk.Canvas(front_card, bg="#f3f1df", highlightthickness=0)
        self.front_canvas.grid(row=0, column=0, sticky="nsew")

        right = ttk.Frame(p, style="Dark.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(6, 4))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)

        msg_card = ttk.Frame(right, style="Card.TFrame", padding=8)
        msg_card.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        msg_card.columnconfigure(0, weight=1)
        msg_card.rowconfigure(0, weight=1)
        self.big_message_label = ttk.Label(msg_card, textvariable=self.big_message_var, style="Good.TLabel", anchor="center", justify="center", wraplength=360, padding=16)
        self.big_message_label.grid(row=0, column=0, sticky="nsew")
        ttk.Label(msg_card, textvariable=self.sensor_var, style="Text.TLabel", wraplength=380).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(msg_card, textvariable=self.pose_var, style="Text.TLabel", wraplength=380).grid(row=2, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(msg_card, text="Clear GUI Emergency Lock", command=self._clear_emergency).grid(row=3, column=0, sticky="ew", pady=(8, 0))

        log_card = ttk.Frame(right, style="Card.TFrame", padding=8)
        log_card.grid(row=1, column=0, sticky="nsew")
        log_card.rowconfigure(0, weight=1)
        log_card.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_card, bg="#050816", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat", font=("Consolas", 9), wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_card, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        cmd_bar = ttk.Frame(log_card, style="Card.TFrame")
        cmd_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        cmd_bar.columnconfigure(0, weight=1)
        ttk.Entry(cmd_bar, textvariable=self.command_var).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(cmd_bar, text="Send", command=self._send_custom).grid(row=0, column=1)

        bottom = ttk.Frame(p, style="Dark.TFrame")
        bottom.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(4, 0))
        bottom.columnconfigure(0, weight=2)
        bottom.columnconfigure(1, weight=5)
        bottom.rowconfigure(0, weight=1)

        controls = ttk.Frame(bottom, style="Card.TFrame", padding=8)
        controls.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._build_buttons(controls)

        map_card = ttk.Frame(bottom, style="Paper.TFrame", padding=6)
        map_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        map_card.columnconfigure(0, weight=1)
        map_card.rowconfigure(0, weight=1)
        self.small_map_canvas = tk.Canvas(map_card, bg="#f3f1df", highlightthickness=0)
        self.small_map_canvas.grid(row=0, column=0, sticky="nsew")

    def _build_full_map_page(self) -> None:
        p = self.full_map_page
        p.columnconfigure(0, weight=1)
        p.rowconfigure(0, weight=1)
        p.rowconfigure(1, weight=0)
        card = ttk.Frame(p, style="Paper.TFrame", padding=8)
        card.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)
        self.big_map_canvas = tk.Canvas(card, bg="#f3f1df", highlightthickness=0)
        self.big_map_canvas.grid(row=0, column=0, sticky="nsew")
        self.big_map_canvas.bind("<ButtonPress-1>", self._start_map_pan)
        self.big_map_canvas.bind("<B1-Motion>", self._drag_map_pan)
        self.big_map_canvas.bind("<ButtonRelease-1>", self._end_map_pan)
        self.big_map_canvas.bind("<MouseWheel>", self._zoom_full_map)   # Windows / macOS
        self.big_map_canvas.bind("<Button-4>", self._zoom_full_map)     # Linux scroll up
        self.big_map_canvas.bind("<Button-5>", self._zoom_full_map)     # Linux scroll down
        bar = ttk.Frame(p, style="Dark.TFrame", padding=6)
        bar.grid(row=1, column=0, sticky="ew")
        ttk.Button(bar, text="Reset GUI Path", command=self._reset_path).pack(side="left", padx=3)
        ttk.Button(bar, text="Reset Map View", command=self._reset_map_view).pack(side="left", padx=3)
        ttk.Button(bar, text="Clear Scan", command=self._clear_scan).pack(side="left", padx=3)
        ttk.Button(bar, text="Clear Map Marks", command=self._clear_marks).pack(side="left", padx=3)
        ttk.Label(bar, textvariable=self.scan_summary_var, style="Text.TLabel").pack(side="right")

    def _build_buttons(self, parent: ttk.Frame) -> None:
        for i in range(4):
            parent.columnconfigure(i, weight=1)
        rows = [
            [("START\nS", "S"), ("STOP\nt", "t"), ("HARD STOP\nX", "X"), ("SCAN 180\ny", "y")],
            [("FWD 10\n1", "1"), ("FWD 20\n2", "2"), ("FWD 30\n3", "3"), ("FWD 40\n4", "4")],
            [("BACK 10\n5", "5"), ("BACK 20\n6", "6"), ("SITE 360\nu", "u"), ("HELP\nH", "H")],
            [("LEFT 5\n7", "7"), ("LEFT 10\n8", "8"), ("LEFT 45\n9", "9"), ("LEFT 90\n0", "0")],
            [("RIGHT 5\nq", "q"), ("RIGHT 10\nw", "w"), ("RIGHT 45\ne", "e"), ("RIGHT 90\nr", "r")],
        ]
        for r, row in enumerate(rows):
            for c, (txt, cmd) in enumerate(row):
                b = ttk.Button(parent, text=txt, command=lambda ch=cmd: self._send_command(ch))
                b.grid(row=r, column=c, sticky="ew", padx=2, pady=2)
                if cmd in "1234567890qwer":
                    self.move_buttons.append(b)
                if cmd in "yu":
                    self.scan_buttons.append(b)
        ttk.Button(parent, text="Reset Path", command=self._reset_path).grid(row=6, column=0, sticky="ew", padx=2, pady=(10, 2))
        ttk.Button(parent, text="Clear Scan", command=self._clear_scan).grid(row=6, column=1, sticky="ew", padx=2, pady=(10, 2))
        ttk.Button(parent, text="Clear Log", command=self._clear_log).grid(row=6, column=2, sticky="ew", padx=2, pady=(10, 2))
        ttk.Button(parent, text="Clear Marks", command=self._clear_marks).grid(row=6, column=3, sticky="ew", padx=2, pady=(10, 2))
        ttk.Label(parent, textvariable=self.scan_summary_var, style="Text.TLabel", wraplength=380).grid(row=7, column=0, columnspan=4, sticky="ew", pady=(8, 0))

    def _bind_keys(self) -> None:
        for ch in list("S1234567890qwertyuHXx"):
            self.root.bind(ch, lambda event, c=ch: self._send_command(c))
        self.root.bind("<space>", lambda event: self._send_command("t"))
        self.root.bind("<Escape>", lambda event: self._send_command("X"))
        self.root.bind("<Return>", lambda event: self._send_custom())

    # ---------------------- socket ----------------------

    def _use_mock(self) -> None:
        self.host_var.set("127.0.0.1")
        self.port_var.set("288")
        self._log("INFO", "Mock selected. Run mock_cybot_server.py first.")

    def _connect(self) -> None:
        if self.sock is not None:
            self._log("INFO", "Already connected")
            return
        try:
            host = self.host_var.get().strip()
            port = int(self.port_var.get().strip())
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((host, port))
            s.settimeout(0.5)
            self.sock = s
            self.stop_reader.clear()
            self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.reader_thread.start()
            self.robot.connected = True
            self.status_var.set(f"Connected to {host}:{port}")
            self._set_message("CONNECTED", "good")
            self._log("CONNECTED", f"{host}:{port}")
        except Exception as exc:
            self.sock = None
            self.robot.connected = False
            self.status_var.set("Connection failed")
            messagebox.showerror("Connection failed", str(exc))
            self._log("ERROR", str(exc))

    def _disconnect(self) -> None:
        self.stop_reader.set()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.robot.connected = False
        self.status_var.set("Disconnected")
        self._log("DISCONNECT", "socket closed")

    def _reader_loop(self) -> None:
        buf = ""
        while not self.stop_reader.is_set():
            try:
                if self.sock is None:
                    break
                data = self.sock.recv(4096)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf or "\r" in buf:
                    places = [i for i in [buf.find("\n"), buf.find("\r")] if i >= 0]
                    cut = min(places)
                    line = buf[:cut].strip()
                    buf = buf[cut + 1:]
                    if line:
                        self.rx_queue.put(line)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as exc:
                self.rx_queue.put(f"GUI_ERROR:{exc}")
                break
        self.rx_queue.put("GUI_DISCONNECTED")

    # ---------------------- commands ----------------------

    def _send_command(self, cmd: str) -> None:
        if not cmd:
            return
        cmd = cmd[0]
        if self.robot.emergency_locked and cmd not in ["t", "X", "x", "H"]:
            self._set_message("LOCKED: use STOP or HARD STOP, then clear lock", "bad")
            self._log("BLOCKED", cmd)
            return
        if self.sock is None:
            self._log("NOT SENT", f"{cmd} (not connected)")
            return
        try:
            self.sock.sendall((cmd + SEND_AFTER_COMMAND).encode("utf-8"))
            self.robot.last_cmd = cmd
            if cmd in ["1", "2", "3", "4"]:
                self.robot.last_direction = 1
            if cmd in ["5", "6"]:
                self.robot.last_direction = -1
            if cmd in ["y", "u"]:
                self._new_scan()
            if cmd in ["X", "x", "t"]:
                self._set_message("STOP SENT", "bad" if cmd in ["X", "x"] else "good")
            self._log("SENT", self._command_name(cmd))
        except OSError as exc:
            self._log("SEND ERR", str(exc))
            self._disconnect()

    def _send_custom(self) -> None:
        text = self.command_var.get().strip()
        if not text:
            return
        for ch in text:
            self._send_command(ch)
        self.command_var.set("")

    def _command_name(self, cmd: str) -> str:
        names = {
            "S": "S start / clear hard stop", "X": "X hard stop", "x": "x hard stop",
            "t": "t normal stop", "y": "y scan 180", "u": "u scan 360", "H": "H help/status",
            "1": "1 forward 10 cm", "2": "2 forward 20 cm", "3": "3 forward 30 cm", "4": "4 forward 40 cm",
            "5": "5 backward 10 cm", "6": "6 backward 20 cm",
            "7": "7 left 5", "8": "8 left 10", "9": "9 left 45", "0": "0 left 90",
            "q": "q right 5", "w": "w right 10", "e": "e right 45", "r": "r right 90",
        }
        return names.get(cmd, cmd)

    # ---------------------- parsing ----------------------

    def _poll_rx(self) -> None:
        try:
            while True:
                line = self.rx_queue.get_nowait()
                if line == "GUI_DISCONNECTED":
                    if self.robot.connected:
                        self.robot.connected = False
                        self.sock = None
                        self.status_var.set("Disconnected")
                        self._log("DISCONNECT", "reader stopped")
                    continue
                self._handle_line(line)
        except queue.Empty:
            pass
        self.root.after(40, self._poll_rx)

    def _handle_line(self, line: str) -> None:
        if "HEARTBEAT" in line.upper() and not SHOW_HEARTBEAT_LINES:
            return
        self._log("RX", line)
        up = line.upper()

        if "SCAN180_START" in up or "SCAN360_START" in up or "SCAN360_FRONT_HALF" in up:
            self._new_scan()
            self._set_message("SCAN STARTED", "good")
        elif line.startswith("GUI_OBJECT"):
            self._parse_object(line)
        elif line.startswith("GUI_SENSOR"):
            self._parse_sensor(line)
        elif line.startswith("NET_MOVEMENT_MM"):
            self._parse_move(line)
        elif line.startswith("TURN_LEFT_DEG"):
            self._parse_turn(line, left=True)
        elif line.startswith("TURN_RIGHT_DEG"):
            self._parse_turn(line, left=False)
        elif "EMERGENCY" in up or "BUMP" in up or "CLIFF" in up or "WHEELDROP" in up or "WHEEL DROP" in up:
            self.robot.emergency_locked = True
            self._set_message(line, "bad")
            self._mark_from_warning(up)
            self._lock_buttons()
        elif "BOUNDARY" in up:
            self.robot.emergency_locked = True
            self._set_message("BOUNDARY DETECTED", "warn")
            self._add_mark_ahead("boundary", "boundary")
            self._lock_buttons()
        elif "MOVE_COMPLETE" in up:
            if not self.robot.emergency_locked:
                self._set_message("MOVE COMPLETE", "good")
        elif "TURN_COMPLETE" in up:
            if not self.robot.emergency_locked:
                self._set_message("TURN COMPLETE", "good")
        elif "SCAN" in up and "COMPLETE" in up:
            if not self.robot.emergency_locked:
                self._set_message("SCAN COMPLETE", "good")
        elif "CYBOT MANUAL MODE READY" in up:
            self._set_message("CYBOT READY", "good")
        elif "HARD_STOP" in up:
            self.robot.emergency_locked = True
            self._set_message("HARD STOP MODE", "bad")
            self._lock_buttons()

        self._update_pose_text()
        self._draw_everything()

    def _parse_object(self, line: str) -> None:
        m = re.search(r"mid\s*=\s*([-+0-9.]+).*?distance\s*=\s*([-+0-9.]+).*?width\s*=\s*([-+0-9.]+)", line)
        if not m:
            return
        angle = float(m.group(1))
        distance = float(m.group(2))
        width = float(m.group(3))
        obj = ScanObject(angle, distance, width, self.scan_id)
        if not obj.valid():
            self._log("IGNORED", f"width {width:.2f} cm is below 1 cm")
            return
        obj.world_x, obj.world_y = self._object_world_position(obj)
        self.scan_objects.append(obj)
        self.map_objects.append(obj)
        self._update_scan_summary()

    def _parse_sensor(self, line: str) -> None:
        pairs = re.findall(r"([A-Za-z]+)=([01])", line.replace(" ", ""))
        self.sensor_values = {k: v for k, v in pairs}
        self.sensor_var.set(" | ".join([f"{k}:{v}" for k, v in self.sensor_values.items()]) if pairs else line)

        bump = self._sensor_on("bumpLeft") or self._sensor_on("bumpRight") or self._sensor_on("bumper")
        cliff = self._sensor_on("cliffLeft") or self._sensor_on("cliffFrontLeft") or self._sensor_on("cliffFrontRight") or self._sensor_on("cliffRight") or self._sensor_on("cliff")
        wheel = self._sensor_on("wheelDropLeft") or self._sensor_on("wheelDropRight")
        boundary = self._sensor_on("boundary")

        if bump:
            self.robot.emergency_locked = True
            self._set_message("BUMP / SHORT OBJECT HIT", "bad")
            self._add_mark_ahead("short", "short object hit")
        if cliff or wheel:
            self.robot.emergency_locked = True
            self._set_message("HOLE / CLIFF DETECTED", "bad")
            self._add_mark_ahead("hole", "hole/cliff")
        if boundary:
            self.robot.emergency_locked = True
            self._set_message("BOUNDARY DETECTED", "warn")
            self._add_mark_ahead("boundary", "boundary")
        if bump or cliff or wheel or boundary:
            self._lock_buttons()
        elif not self.robot.emergency_locked:
            self._set_message("SENSORS OK", "good")

    def _sensor_on(self, key: str) -> bool:
        return self.sensor_values.get(key) == "1"

    def _parse_move(self, line: str) -> None:
        m = re.search(r"NET_MOVEMENT_MM\s*:\s*([-+0-9.]+)", line)
        if not m:
            return
        mm = float(m.group(1))
        cm = abs(mm) / 10.0
        direction = -1 if self.robot.last_cmd in ["5", "6"] or mm < 0 else self.robot.last_direction
        rad = math.radians(self.robot.heading)
        self.robot.x += direction * cm * math.sin(rad)
        self.robot.y += direction * cm * math.cos(rad)
        # Do not clamp the relative position to the original map border.
        # The full-map page can be panned to view objects/path outside the initial border.
        self.robot.path.append((self.robot.x, self.robot.y))

    def _parse_turn(self, line: str, left: bool) -> None:
        m = re.search(r"TURN_(LEFT|RIGHT)_DEG\s*:\s*([-+0-9.]+)", line)
        if not m:
            return
        deg = float(m.group(2))
        if left:
            self.robot.heading = (self.robot.heading - deg) % 360
        else:
            self.robot.heading = (self.robot.heading + deg) % 360

    def _mark_from_warning(self, upper_line: str) -> None:
        if "BUMP" in upper_line:
            self._add_mark_ahead("short", "short object hit")
        if "CLIFF" in upper_line or "WHEEL" in upper_line or "HOLE" in upper_line:
            self._add_mark_ahead("hole", "hole/cliff")
        if "BOUNDARY" in upper_line:
            self._add_mark_ahead("boundary", "boundary")

    # ---------------------- map helpers ----------------------

    def _object_world_position(self, obj: ScanObject) -> Tuple[float, float]:
        # Scan convention used by the GUI:
        # 0 degrees = right, 90 degrees = straight ahead, 180 degrees = left.
        # Robot heading convention:
        # 0 degrees = forward/up on the relative map, positive turns right/clockwise.
        #
        # The old code used obj.angle - 90, which mirrored left/right on the map.
        # 90 - obj.angle fixes that: angle 0 goes to the robot's right, angle 180 goes left.
        relative = 90.0 - obj.angle
        absolute = self.robot.heading + relative
        rad = math.radians(absolute)

        # Scan distance is the closest point on the object, not the object's center.
        # So the object's center is:
        #   distance past CyBot front edge + half of the object's linear width.
        # The CyBot is 36cm wide, so the front edge is about 18cm ahead of the epicenter.
        map_distance = obj.distance + (CYBOT_WIDTH_CM / 2.0) + (obj.width / 2.0)

        x = self.robot.x + map_distance * math.sin(rad)
        y = self.robot.y + map_distance * math.cos(rad)
        return x, y

    def _add_mark_ahead(self, kind: str, label: str) -> None:
        # Put sensor event marks just past the front edge of the robot.
        # The CyBot is 36cm wide, so its front edge is about 18cm from the epicenter.
        distance = (CYBOT_WIDTH_CM / 2.0) + 3.0
        rad = math.radians(self.robot.heading)
        x = self.robot.x + distance * math.sin(rad)
        y = self.robot.y + distance * math.cos(rad)
        x = max(0, min(MAP_W_CM, x))
        y = max(0, min(MAP_H_CM, y))
        self.map_marks.append(MapMark(x, y, kind, label))

    def _new_scan(self) -> None:
        self.scan_id += 1
        self.scan_objects.clear()
        # Keep the learned near objects on the relative map, but remove far/vague hints.
        # Far objects are not reliable enough to persist after another scan starts.
        self.map_objects = [obj for obj in self.map_objects if obj.near()]
        self._update_scan_summary()

    def _update_scan_summary(self) -> None:
        near = [o for o in self.scan_objects if o.near()]
        far = [o for o in self.scan_objects if not o.near()]
        pillars = [o for o in self.scan_objects if o.pillar_hint()]
        self.scan_summary_var.set(f"Scan {self.scan_id}: {len(near)} near <=50cm | {len(far)} far hints | {len(pillars)} green pillar hints")

    def _update_pose_text(self) -> None:
        self.pose_var.set(f"Relative pose: x={self.robot.x:.1f}cm, y={self.robot.y:.1f}cm, heading={self.robot.heading:.1f}°. CyBot shown to scale on map.")

    # ---------------------- drawing ----------------------

    def _redraw_timer(self) -> None:
        self._draw_everything()
        self.root.after(300, self._redraw_timer)

    def _draw_everything(self) -> None:
        self._draw_front()
        self._draw_map(self.small_map_canvas, full=False)
        self._draw_map(self.big_map_canvas, full=True)

    def _object_radius(self, obj: ScanObject, far_small: bool = False) -> float:
        if obj.pillar_hint():
            base = max(MIN_OBJECT_PIXEL_RADIUS, obj.width * PILLAR_PIXEL_SCALE)
        else:
            base = max(MIN_OBJECT_PIXEL_RADIUS, obj.width * OBJECT_WIDTH_PIXEL_SCALE)
        base = min(MAX_OBJECT_PIXEL_RADIUS, base)
        if far_small:
            base = max(2, min(6, base * 0.25))
        return base

    def _front_display_distance(self, distance_cm: float) -> float:
        # Display scaling only:
        # The scan view max is 100 cm.
        # 0-50 real cm is expanded linearly into 0-FRONT_FOCUS_DISPLAY_CM.
        # 50-100 real cm is compressed into the remaining display space.
        # The real distance is still unchanged everywhere else.
        d = max(0.0, min(FAR_LIMIT_CM, distance_cm))
        if d <= NEAR_LIMIT_CM:
            return (d / NEAR_LIMIT_CM) * FRONT_FOCUS_DISPLAY_CM
        remaining_real = FAR_LIMIT_CM - NEAR_LIMIT_CM
        remaining_display = FAR_LIMIT_CM - FRONT_FOCUS_DISPLAY_CM
        return FRONT_FOCUS_DISPLAY_CM + ((d - NEAR_LIMIT_CM) / remaining_real) * remaining_display

    def _draw_front(self) -> None:
        c = self.front_canvas
        c.delete("all")
        w = max(c.winfo_width(), 720)
        h = max(c.winfo_height(), 520)
        cx = w / 2
        cy = h - 48
        radius = min(w * 0.48, h * 0.86)

        for x in range(0, int(w), 45):
            c.create_line(x, 0, x, h, fill="#e0deca")
        for y in range(0, int(h), 45):
            c.create_line(0, y, w, y, fill="#e0deca")

        # 50 cm is the main focus ring.
        # The scan max is 100 cm, and 0-50 cm is expanded linearly.
        # This improves close-distance readability without changing real distance values.
        for r_cm in [10, 25, 50, 75, 100]:
            rr = radius * self._front_display_distance(r_cm) / FAR_LIMIT_CM
            if r_cm == 50:
                c.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=0, extent=180, outline="#111827", width=4)
                c.create_text(cx + rr + 20, cy - 8, text="50 cm focus", fill="#111827", font=("Segoe UI", 11, "bold"))
            else:
                c.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=0, extent=180, outline="#9ca3af", width=1, dash=(5, 6))
                c.create_text(cx + rr + 8, cy - 5, text=f"{r_cm}", fill="#6b7280", font=("Segoe UI", 8))

        for deg in range(0, 181, 30):
            # Polar scan convention: 0 degrees is right, 90 is straight ahead, 180 is left.
            theta = math.radians(deg)
            x = cx + radius * math.cos(theta)
            y = cy - radius * math.sin(theta)
            c.create_line(cx, cy, x, y, fill="#c7c5b3", dash=(5, 7))
            c.create_text(x, y, text=str(deg), fill="#4b5563", font=("Segoe UI", 9))

        # CyBot size at scanner origin.
        # Width is based on CYBOT_WIDTH_CM, so the robot is drawn as a 36 cm wide circle.
        size = max(24.0, radius * (self._front_display_distance(CYBOT_WIDTH_CM) / FAR_LIMIT_CM) * FRONT_CYBOT_PIXEL_SCALE)
        cybot_r = size / 2.0
        # Align the front/top edge of the CyBot circle with the bottom edge
        # of the scan semicircle. In this view, the CyBot sits just below
        # the scan origin/diameter line, so it does not cover the 0-50cm grid.
        cybot_top_y = cy
        cybot_cy = cybot_top_y + cybot_r + FRONT_CYBOT_Y_OFFSET_PX
        c.create_oval(cx - cybot_r, cybot_cy - cybot_r, cx + cybot_r, cybot_cy + cybot_r, fill="#bfdbfe", outline="#111827", width=3)
        c.create_line(cx, cybot_cy, cx, cybot_cy - cybot_r * 0.85, fill="#111827", width=3)
        c.create_polygon(cx, cybot_cy - cybot_r * 1.15, cx - cybot_r * 0.22, cybot_cy - cybot_r * 0.75, cx + cybot_r * 0.22, cybot_cy - cybot_r * 0.75, fill="#38bdf8", outline="#111827", width=2)
        c.create_text(cx, cybot_cy + cybot_r + 18, text="CyBot width: 36cm", fill="#111827", font=("Segoe UI", 12, "bold"))

        # Red width highlight for the CyBot: 36 cm total = 18 cm from epicenter on each side.
        half_width_px = radius * (self._front_display_distance(CYBOT_WIDTH_CM / 2.0) / FAR_LIMIT_CM)
         # Draw the width marker centered on the epicenter / scanner origin line.
        width_y = cy + 2
        c.create_line(
            cx - half_width_px, width_y,
            cx + half_width_px, width_y,
            fill="#dc2626", width=6
        )

        # End caps
        c.create_line(
            cx - half_width_px, width_y - 10,
            cx - half_width_px, width_y + 10,
            fill="#dc2626", width=4
        )
        c.create_line(
            cx + half_width_px, width_y - 10,
            cx + half_width_px, width_y + 10,
            fill="#dc2626", width=4
        )

        # Center tick at epicenter
        c.create_line(
            cx, width_y - 12,
            cx, width_y + 12,
            fill="#991b1b", width=4
        )

        # Labels
        c.create_text(
            cx, width_y + 18,
            text="CyBot width = 36 cm",
            fill="#991b1b",
            font=("Segoe UI", 10, "bold")
        )
        c.create_text(
            cx - half_width_px / 2, width_y - 14,
            text="18 cm",
            fill="#991b1b",
            font=("Segoe UI", 9, "bold")
        )
        c.create_text(
            cx + half_width_px / 2, width_y - 14,
            text="18 cm",
            fill="#991b1b",
            font=("Segoe UI", 9, "bold")
        )

        # Draw far first, near last.
        objects = sorted(self.scan_objects, key=lambda o: o.near())
        for obj in objects:
            if not obj.valid():
                continue
            dist = min(obj.distance, FAR_LIMIT_CM)
            display_dist = self._front_display_distance(dist)
            rr = radius * display_dist / FAR_LIMIT_CM
            # Polar scan convention: 0 degrees is right, 90 is straight ahead, 180 is left.
            theta = math.radians(obj.angle)
            x = cx + rr * math.cos(theta)
            y = cy - rr * math.sin(theta)

            if obj.near():
                fill = "#22c55e" if obj.pillar_hint() else "#9ca3af"
                outline = "#14532d" if obj.pillar_hint() else "#111827"
                rad = self._object_radius(obj)
                c.create_oval(x - rad, y - rad, x + rad, y + rad, fill=fill, outline=outline, width=3)
                c.create_text(x, y - rad - 15, text=f"{obj.distance:.0f}cm / w{obj.width:.1f}", fill="#111827", font=("Segoe UI", 10, "bold"))
            else:
                rad = self._object_radius(obj, far_small=True)
                fill = "#86efac" if obj.pillar_hint() else "#d1d5db"
                c.create_oval(x - rad, y - rad, x + rad, y + rad, fill=fill, outline="#6b7280")

        c.create_rectangle(10, 10, 440, 76, fill="#f9faf0", outline="#9ca3af")
        c.create_oval(24, 25, 44, 45, fill="#22c55e", outline="#14532d", width=2)
        c.create_text(54, 35, anchor="w", text="1-5 cm width = possible destination pillar", fill="#111827", font=("Segoe UI", 10, "bold"))
        c.create_oval(24, 50, 44, 70, fill="#9ca3af", outline="#111827", width=2)
        c.create_text(54, 60, anchor="w", text="normal scan object = gray; red only means hit/hole", fill="#111827", font=("Segoe UI", 10, "bold"))

    def _map_xy(self, canvas: tk.Canvas, x: float, y: float) -> Tuple[float, float]:
        w = max(canvas.winfo_width(), 500)
        h = max(canvas.winfo_height(), 240)
        pad = 28

        if hasattr(self, "big_map_canvas") and canvas is self.big_map_canvas:
            # Full-map view uses one uniform cm-to-pixel scale so grid cells are true squares
            # and the 8.4m x 8.4m border is drawn as a square, not stretched.
            scale = min((w - pad * 2) / MAP_W_CM, (h - pad * 2) / MAP_H_CM) * self.map_zoom
            field_w_px = MAP_W_CM * scale
            field_h_px = MAP_H_CM * scale
            left = (w - field_w_px) / 2.0 + self.map_pan_x
            bottom = (h + field_h_px) / 2.0 + self.map_pan_y
            return left + x * scale, bottom - y * scale

        sx = (w - pad * 2) / MAP_W_CM
        sy = (h - pad * 2) / MAP_H_CM
        return pad + x * sx, h - pad - y * sy

    def _draw_map(self, c: tk.Canvas, full: bool) -> None:
        c.delete("all")
        w = max(c.winfo_width(), 500)
        h = max(c.winfo_height(), 240)
        pad = 28
        if full:
            # Full-map-only view shows the full 8.4m x 8.4m field border.
            # The border and grid pan together so you can drag around the large field.
            border_left, border_bottom = self._map_xy(c, 0, 0)
            border_right, border_top = self._map_xy(c, MAP_W_CM, MAP_H_CM)
            left = min(border_left, border_right)
            right = max(border_left, border_right)
            top = min(border_top, border_bottom)
            bottom = max(border_top, border_bottom)

            grid_cm = 50.0
            # Uniform grid scale: 50cm by 50cm grid cells are drawn as real squares.
            cm_to_px = (right - left) / MAP_W_CM
            grid_px = max(8.0, grid_cm * cm_to_px)

            x = left
            while x <= right:
                c.create_line(x, top, x, bottom, fill="#e0deca", dash=(8, 12))
                x += grid_px
            y = top
            while y <= bottom:
                c.create_line(left, y, right, y, fill="#e0deca", dash=(8, 12))
                y += grid_px

            c.create_rectangle(left, top, right, bottom, outline="#111827", width=3)
            c.create_text(left + 10, top + 10, anchor="nw", text="8.4m x 8.4m relative field border. Drag to pan.", fill="#374151", font=("Segoe UI", 9, "bold"))
        else:
            # Small map stays as a compact local overview with a simple border.
            left, top = pad, pad
            right, bottom = w - pad, h - pad
            spacing = 45
            for x in range(int(left), int(right), spacing):
                c.create_line(x, top, x, bottom, fill="#e0deca", dash=(8, 12))
            for y in range(int(top), int(bottom), spacing):
                c.create_line(left, y, right, y, fill="#e0deca", dash=(8, 12))
            c.create_rectangle(left, top, right, bottom, outline="#111827", width=2)
            c.create_text(left + 10, top + 10, anchor="nw", text="Relative 8.4m x 8.4m map; marks are added only after movement/scans/sensors", fill="#374151", font=("Segoe UI", 9, "bold"))

        # Full-map scaling for real-size objects.
        # On the full map, scan objects, pillars, holes, boundaries, and CyBot scale with zoom.
        if full:
            map_cm_to_px = (right - left) / MAP_W_CM
        else:
            map_cm_to_px = None

        # Path.
        if len(self.robot.path) >= 2:
            points: List[float] = []
            for px, py in self.robot.path:
                mx, my = self._map_xy(c, px, py)
                points.extend([mx, my])
            c.create_line(*points, fill="#2563eb", width=3 if not full else 5, smooth=True)
        for px, py in self.robot.path[-60:]:
            mx, my = self._map_xy(c, px, py)
            c.create_oval(mx - 2, my - 2, mx + 2, my + 2, fill="#1d4ed8", outline="")

        # Learned scan objects. These are intentionally NOT cleared after each new scan.
        for obj in self.map_objects:
            if obj.world_x is None or obj.world_y is None or not obj.valid():
                continue
            mx, my = self._map_xy(c, obj.world_x, obj.world_y)
            far = not obj.near()

            if full and map_cm_to_px is not None:
                # Full map uses real object width in cm. Diameter = object linear width.
                rad = max(1.0, (obj.width * map_cm_to_px) / 2.0)
            else:
                rad = self._object_radius(obj, far_small=far)

            if obj.pillar_hint():
                fill = "#22c55e" if obj.near() else "#bbf7d0"
                outline = "#14532d"
            else:
                fill = "#9ca3af" if obj.near() else "#d1d5db"
                outline = "#374151"
            c.create_oval(mx - rad, my - rad, mx + rad, my + rad, fill=fill, outline=outline, width=2 if obj.near() else 1)

        # Hit/hole/boundary marks.
        for mark in self.map_marks:
            mx, my = self._map_xy(c, mark.x, mark.y)

            if full and map_cm_to_px is not None:
                hole_r = max(1.0, (HIT_HOLE_DIAMETER_CM * map_cm_to_px) / 2.0)
                boundary_r = max(1.0, (BOUNDARY_DIAMETER_CM * map_cm_to_px) / 2.0)
            else:
                hole_r = 13.0
                boundary_r = 10.0

            if mark.kind == "boundary":
                fill = "#7e22ce"   # nasty purple, 5 cm diameter on full map
                outline = "#3b0764"
                c.create_oval(mx - boundary_r, my - boundary_r, mx + boundary_r, my + boundary_r, fill=fill, outline=outline, width=2)
            elif mark.kind == "hole":
                fill = "#dc2626"   # 13 cm diameter on full map
                c.create_oval(mx - hole_r, my - hole_r, mx + hole_r, my + hole_r, fill=fill, outline="#7f1d1d", width=2)
            else:
                fill = "#ef4444"   # short object hit, use same 13 cm diameter assumption
                c.create_oval(mx - hole_r, my - hole_r, mx + hole_r, my + hole_r, fill=fill, outline="#7f1d1d", width=2)
            if full:
                label_offset = max(8.0, hole_r + 4.0)
                c.create_text(mx + label_offset, my, anchor="w", text=mark.label, fill="#111827", font=("Segoe UI", 9, "bold"))

        # CyBot on map.
        # Drawn 36 cm wide using the same uniform cm-to-pixel scale as the field.
        mx, my = self._map_xy(c, self.robot.x, self.robot.y)
        map_w = max(c.winfo_width(), 500)
        map_h = max(c.winfo_height(), 240)
        map_pad = 28
        if full:
            # Exact full-map scale: CyBot diameter/width is 36 cm and grows/shrinks with zoom.
            cm_to_px = map_cm_to_px if map_cm_to_px is not None else min((map_w - map_pad * 2) / MAP_W_CM, (map_h - map_pad * 2) / MAP_H_CM) * self.map_zoom
            cybot_width_px = max(2.0, CYBOT_WIDTH_CM * cm_to_px)
        else:
            map_sx = (map_w - map_pad * 2) / MAP_W_CM
            map_sy = (map_h - map_pad * 2) / MAP_H_CM
            cm_to_px = min(map_sx, map_sy)
            cybot_width_px = max(12.0, CYBOT_WIDTH_CM * cm_to_px * MAP_CYBOT_PIXEL_SCALE)
        cybot_rad = cybot_width_px / 2.0
        heading = math.radians(self.robot.heading)
        tip = (mx + cybot_width_px * 0.75 * math.sin(heading), my - cybot_width_px * 0.75 * math.cos(heading))
        leftp = (mx + cybot_rad * math.sin(heading + 2.4), my - cybot_rad * math.cos(heading + 2.4))
        rightp = (mx + cybot_rad * math.sin(heading - 2.4), my - cybot_rad * math.cos(heading - 2.4))
        c.create_oval(mx - cybot_rad, my - cybot_rad, mx + cybot_rad, my + cybot_rad, fill="#bfdbfe", outline="#111827", width=2)
        c.create_polygon(tip, leftp, rightp, fill="#38bdf8", outline="#111827", width=2)
        c.create_text(mx + cybot_rad + 6, my, anchor="w", text="CyBot 36cm", fill="#111827", font=("Segoe UI", 9, "bold"))

        # Map legend.
        ly = bottom - 52
        c.create_rectangle(left + 8, ly - 12, left + 430, ly + 36, fill="#f9faf0", outline="#9ca3af")
        c.create_oval(left + 20, ly, left + 34, ly + 14, fill="#22c55e", outline="#14532d")
        c.create_text(left + 42, ly + 7, anchor="w", text="pillar hint", fill="#111827", font=("Segoe UI", 8))
        c.create_oval(left + 120, ly, left + 134, ly + 14, fill="#9ca3af", outline="#374151")
        c.create_text(left + 142, ly + 7, anchor="w", text="scan object", fill="#111827", font=("Segoe UI", 8))
        c.create_polygon(left + 230, ly, left + 244, ly + 14, left + 216, ly + 14, fill="#ef4444", outline="#7f1d1d")
        c.create_text(left + 252, ly + 7, anchor="w", text="hit/hole", fill="#111827", font=("Segoe UI", 8))
        c.create_rectangle(left + 330, ly, left + 344, ly + 14, fill="#7e22ce", outline="#3b0764")
        c.create_text(left + 352, ly + 7, anchor="w", text="boundary", fill="#111827", font=("Segoe UI", 8))

    # ---------------------- small helpers ----------------------

    def _set_message(self, msg: str, level: str) -> None:
        if level == "bad":
            self.big_message_label.configure(style="Bad.TLabel")
            self.big_message_var.set(msg)
        elif level == "warn":
            self.big_message_label.configure(style="Warn.TLabel")
            self.big_message_var.set(msg)
        else:
            if not self.robot.emergency_locked:
                self.big_message_label.configure(style="Good.TLabel")
                self.big_message_var.set(msg)

    def _lock_buttons(self) -> None:
        state = "disabled" if self.robot.emergency_locked else "normal"
        for b in self.move_buttons + self.scan_buttons:
            b.configure(state=state)

    def _clear_emergency(self) -> None:
        self.robot.emergency_locked = False
        self._lock_buttons()
        self._set_message("GUI lock cleared. Check CyBot before moving.", "good")

    def _reset_path(self) -> None:
        self.robot.x = START_X_CM
        self.robot.y = START_Y_CM
        self.robot.heading = 0.0
        self.robot.path = [(START_X_CM, START_Y_CM)]
        # Reset Path is the big relative-map reset. It clears learned objects and marks too.
        self.map_objects.clear()
        self.map_marks.clear()
        self.scan_objects.clear()
        self._update_scan_summary()
        self._update_pose_text()
        self._draw_everything()
        self._log("GUI", "path and relative map objects reset in GUI")

    def _clear_scan(self) -> None:
        self.scan_objects.clear()
        # Clear Scan removes only the current scan view and far/vague map hints.
        # Near learned objects remain on the relative map.
        self.map_objects = [obj for obj in self.map_objects if obj.near()]
        self._update_scan_summary()
        self._draw_everything()

    def _clear_marks(self) -> None:
        self.map_marks.clear()
        # Clear Marks also removes far/vague objects from the relative map.
        # Near learned objects stay because they are useful obstacles.
        self.map_objects = [obj for obj in self.map_objects if obj.near()]
        self._draw_everything()

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def _start_map_pan(self, event: tk.Event) -> None:
        self.map_drag_start = (float(event.x), float(event.y))

    def _drag_map_pan(self, event: tk.Event) -> None:
        if self.map_drag_start is None:
            return
        old_x, old_y = self.map_drag_start
        dx = float(event.x) - old_x
        dy = float(event.y) - old_y
        self.map_pan_x += dx
        self.map_pan_y += dy
        self.map_drag_start = (float(event.x), float(event.y))
        self._draw_map(self.big_map_canvas, full=True)

    def _end_map_pan(self, event: tk.Event) -> None:
        self.map_drag_start = None

    def _reset_map_view(self) -> None:
        self.map_pan_x = 0.0
        self.map_pan_y = 0.0
        self.map_zoom = 1.0
        self._draw_map(self.big_map_canvas, full=True)

    def _zoom_full_map(self, event: tk.Event) -> str:
        # Scroll wheel zooms the full-map-only page.
        # Zoom is centered around the mouse cursor so the spot under your mouse stays stable.
        old_zoom = self.map_zoom

        if hasattr(event, "num") and event.num == 4:
            zoom_factor = 1.12
        elif hasattr(event, "num") and event.num == 5:
            zoom_factor = 1.0 / 1.12
        elif getattr(event, "delta", 0) > 0:
            zoom_factor = 1.12
        else:
            zoom_factor = 1.0 / 1.12

        new_zoom = max(0.25, min(8.0, old_zoom * zoom_factor))
        if new_zoom == old_zoom:
            return "break"

        mouse_x = float(event.x)
        mouse_y = float(event.y)

        # Adjust pan so the map zooms around the mouse position instead of the center.
        self.map_pan_x = mouse_x - ((mouse_x - self.map_pan_x) * (new_zoom / old_zoom))
        self.map_pan_y = mouse_y - ((mouse_y - self.map_pan_y) * (new_zoom / old_zoom))
        self.map_zoom = new_zoom

        self._draw_map(self.big_map_canvas, full=True)
        return "break"

    def _log(self, tag: str, msg: str) -> None:
        self.log_text.insert(tk.END, f"{tag:<9} {msg}\n")
        self.log_text.see(tk.END)

    def _quick_demo(self) -> None:
        self._clear_emergency()
        self._new_scan()
        demo = [
            "CYBOT MANUAL MODE READY",
            "EVENT:SCAN180_START,threshold=110",
            "GUI_OBJECT,mid=40,distance=34,width=3.0",
            "GUI_OBJECT,mid=72,distance=42,width=18.0",
            "GUI_OBJECT,mid=116,distance=48,width=45.0",
            "GUI_OBJECT,mid=145,distance=92,width=5.0",
            "GUI_OBJECT,mid=150,distance=44,width=0.4",
            "EVENT:SCAN180_COMPLETE",
            "NET_MOVEMENT_MM:100.00",
            "TURN_RIGHT_DEG:45.00",
            "NET_MOVEMENT_MM:150.00",
            "GUI_SENSOR,bumper=1,cliff=0,boundary=0,bumpLeft=1,bumpRight=0,cliffLeft=0,cliffFrontLeft=0,cliffFrontRight=0,cliffRight=0,wheelDropLeft=0,wheelDropRight=0",
        ]
        for line in demo:
            self._handle_line(line)
        self._set_message("DEMO LOADED", "good")


def main() -> None:
    root = tk.Tk()
    app = CyBotGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app._disconnect(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
