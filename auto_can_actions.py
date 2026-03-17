import can
import subprocess
import time
import math
from datetime import datetime

VCAN = "vcan0"

SPEED_ID = 0x3EA
SIGNAL_ID = 0x47D
DOOR_ID = 0x474

KMH_PER_MPH = 1.60934

last_speed_mph = None


def now_str():
    return datetime.now().strftime("%H:%M:%S")


def log(msg):
    print(f"[{now_str()}] {msg}", flush=True)


def popup(msg):
    subprocess.run(["notify-send", msg], check=False)


def mph_to_kmh(mph):
    return mph * KMH_PER_MPH


def trigger_mph_from_target_kmh(target_kmh):
    # lấy mốc gần nhất nhưng KHÔNG vượt target
    return math.floor(target_kmh / KMH_PER_MPH)


def send_frame(bus, can_id, data, desc, repeat=3, delay=0.05):
    msg = can.Message(
        arbitration_id=can_id,
        data=data,
        is_extended_id=False
    )

    try:
        for _ in range(repeat):
            bus.send(msg)
            time.sleep(delay)

        log(f"[ACTION] {desc} -> sent {repeat}x {can_id:03X}#{data.hex().upper()}")

    except can.CanError as e:
        log(f"[ERROR] Cannot send {can_id:03X}#{data.hex().upper()} | {e}")


def send_right_signal(bus):
    send_frame(
        bus,
        SIGNAL_ID,
        bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x02]),
        "Turn RIGHT signal ON"
    )


def open_all_doors(bus):
    send_frame(
        bus,
        DOOR_ID,
        bytes([0x00]),
        "Open ALL doors"
    )


MILESTONES = [
    {
        "target_kmh": 30.0,
        "popup_text": "Vehicle is near 30 km/h",
        "action": None,
        "done": False,
    },
    {
        "target_kmh": 60.0,
        "popup_text": "Vehicle is near 60 km/h - Turn right signal ON",
        "action": send_right_signal,
        "done": False,
    },
    {
        "target_kmh": 90.0,
        "popup_text": "Vehicle is near 90 km/h - Open all doors",
        "action": open_all_doors,
        "done": False,
    },
]

for m in MILESTONES:
    m["trigger_mph"] = trigger_mph_from_target_kmh(m["target_kmh"])
    m["trigger_kmh"] = mph_to_kmh(m["trigger_mph"])


def main():
    global last_speed_mph

    try:
        bus = can.interface.Bus(channel=VCAN, interface="socketcan")
    except Exception as e:
        log(f"[FATAL] Cannot open {VCAN}: {e}")
        return

    log("[START] Listening for speed frames on 0x3EA")
    for m in MILESTONES:
        log(
            f"[INIT] target {m['target_kmh']:.1f} km/h"
            f" -> trigger at closest <= value: {m['trigger_mph']} mph ({m['trigger_kmh']:.1f} km/h)"
        )

    while True:
        try:
            msg = bus.recv()
        except KeyboardInterrupt:
            log("[EXIT] Stopped by user")
            break
        except Exception as e:
            log(f"[ERROR] recv failed: {e}")
            continue

        if not msg or msg.arbitration_id != SPEED_ID:
            continue

        if len(msg.data) != 7:
            continue

        speed_mph = msg.data[6]
        speed_kmh = mph_to_kmh(speed_mph)

        if speed_mph != last_speed_mph:
            log(f"[SPEED] {speed_mph} mph | {speed_kmh:.1f} km/h")
            last_speed_mph = speed_mph

        for m in MILESTONES:
            if speed_mph < m["trigger_mph"]:
                m["done"] = False

            if speed_mph >= m["trigger_mph"] and not m["done"]:
                popup(m["popup_text"])
                log(
                    f"[MILESTONE] near {m['target_kmh']:.1f} km/h"
                    f" -> triggered at {m['trigger_kmh']:.1f} km/h ({m['trigger_mph']} mph)"
                )

                if m["action"] is not None:
                    m["action"](bus)

                m["done"] = True


if __name__ == "__main__":
    main()