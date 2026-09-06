"""Mock CyBot server for testing cybot_final_gui.py without the physical robot.
Run this first, then run the GUI and connect to 127.0.0.1:288.
This mock follows the current uploaded main.c command protocol.
"""

from __future__ import annotations

import socket
import threading
import time

HOST = "127.0.0.1"
PORT = 288

MOVE_MM = {"1": 100.47, "2": 201.39, "3": 302.08, "4": 400.78, "5": 108.70, "6": 202.28}
LEFT_DEG = {"7": 6.08, "8": 10.85, "9": 45.43, "0": 92.16}
RIGHT_DEG = {"q": 5.48, "w": 11.09, "e": 46.26, "r": 91.81}


def send(conn: socket.socket, text: str, delay: float = 0.05) -> None:
    conn.sendall(text.encode("utf-8"))
    time.sleep(delay)


def send_scan180(conn: socket.socket, objects=None) -> None:
    if objects is None:
        objects = [
            (18, 82, 6.1),
            (69, 104, 67.0),
            (116, 120, 42.5),
        ]
    send(conn, "\r\nEVENT:SCAN180_START,threshold=110\r\n")
    # Some scan points, not all 91, enough to test the graph.
    for angle in range(0, 181, 6):
        ir = 150
        ping = 150
        for mid, dist, width in objects:
            if abs(angle - mid) < max(4, width / 5):
                ir = int(dist)
                ping = int(dist + 3)
        send(conn, f"SCAN_POINT,angle={angle},ping={ping},ir_cm={ir},adc_raw={900 + angle}\r\n", 0.003)
    for mid, dist, width in objects:
        send(conn, f"GUI_OBJECT,mid={mid},distance={dist},width={width:.2f}\r\n", 0.04)
    send(conn, f"GUI_OBJECT_COUNT,{len(objects)}\r\n")
    send(conn, "EVENT:SCAN180_COMPLETE\r\n")


def send_emergency(conn: socket.socket) -> None:
    send(conn, "\r\nEMERGENCY DETECTED\r\n")
    send(conn, " Detected cliffFrontRight\r\n")
    send(conn, "GUI_SENSOR,bumper=0,cliff=1,boundary=1,bumpLeft=0,bumpRight=0,cliffLeft=0,cliffFrontLeft=0,cliffFrontRight=1,cliffRight=0,wheelDropLeft=0,wheelDropRight=0\r\n")


def handle_client(conn: socket.socket, addr) -> None:
    print(f"Client connected: {addr}")
    with conn:
        send(conn, "\r\nEVENT:SCAN_SYSTEM_READY\r\n")
        send(conn, "\r\nCYBOT MANUAL MODE READY\r\n")
        while True:
            data = conn.recv(1)
            if not data:
                break
            cmd = data.decode("ascii", errors="ignore")
            print(f"got command: {cmd!r}")
            send(conn, cmd, 0.01)  # current UART echoes the byte

            if cmd == "S":
                send(conn, "\r\nMISSION STARTED MOCK\r\n")
            elif cmd in MOVE_MM:
                # Uncomment the next 2 lines if you want to test emergency behavior.
                # if cmd == "4":
                #     send_emergency(conn); continue
                send(conn, "\r\nEVENT:MOVE_COMPLETE\r\n")
                send(conn, f"NET_MOVEMENT_MM:{MOVE_MM[cmd]:.2f}\r\n")
            elif cmd in LEFT_DEG:
                send(conn, "\r\nEVENT:TURN_COMPLETE\r\n")
                send(conn, f"TURN_LEFT_DEG:{LEFT_DEG[cmd]:.2f}\r\n")
            elif cmd in RIGHT_DEG:
                send(conn, "\r\nEVENT:TURN_COMPLETE\r\n")
                send(conn, f"TURN_RIGHT_DEG:{RIGHT_DEG[cmd]:.2f}\r\n")
            elif cmd == "t":
                send(conn, "\r\nEVENT:STOP\r\n")
            elif cmd == "y":
                send_scan180(conn)
            elif cmd == "u":
                send(conn, "\r\nEVENT:SCAN360_START\r\n")
                send(conn, "\r\nEVENT:SCAN360_FRONT_HALF\r\n")
                send_scan180(conn, objects=[(18, 82, 6.1), (69, 104, 67.0), (116, 120, 42.5)])
                send(conn, "\r\nEVENT:SCAN360_TURNING_180\r\n")
                send(conn, "\r\nEVENT:TURN_COMPLETE\r\n")
                send(conn, "TURN_RIGHT_DEG:180.51\r\n")
                send(conn, "\r\nEVENT:SCAN360_BACK_HALF\r\n")
                send_scan180(conn, objects=[(44, 76, 7.5), (142, 93, 30.0)])
                send(conn, "\r\nEVENT:SCAN360_COMPLETE,total_objects=5,front_objects=3,back_objects=2\r\n")
                send(conn, "\r\nEVENT:TURN_COMPLETE\r\n")
                send(conn, "TURN_LEFT_DEG:181.94\r\n")
            elif cmd == "H":
                send(conn, "\r\nManual control commands: 1-4 forward, 5-6 back, 7-0 left, q-r right, t stop, y scan180, u scan360\r\n")

    print(f"Client disconnected: {addr}")


def main() -> None:
    print(f"Mock CyBot server running on {HOST}:{PORT}")
    print("Run cybot_final_gui.py, click 'Use Mock', then Connect.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)
        while True:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
