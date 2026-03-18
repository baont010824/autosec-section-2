import can
import subprocess
import time
from datetime import datetime

VCAN = "vcan0"

SPEED_ID = 0x3EA
SIGNAL_ID = 0x47D
DOOR_ID = 0x474

KMH_TO_MPH = 0.6213751
SPEED_POS = 6

last_speed_raw = None


def now_str():
    return datetime.now().strftime("%H:%M:%S")


def log(msg):
    print(f"[{now_str()}] {msg}", flush=True)


def popup(msg):
    subprocess.run(["notify-send", msg], check=False)


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


def normalize_speed_payload(data):
    """
    Chuẩn hóa payload speed:
    - 8 byte: dùng nguyên
    - 7 byte: pad thêm 0x00 ở cuối
    - <7 byte: bỏ
    """
    dlc = len(data)

    if dlc >= 8:
        return bytes(data[:8])

    if dlc == 7:
        return bytes(data) + b"\x00"

    return None


def decode_icsim_speed(msg):
    payload = normalize_speed_payload(msg.data)
    if payload is None:
        return None, None, None

    raw = (payload[SPEED_POS] << 8) | payload[SPEED_POS + 1]
    speed_kmh = raw / 100.0
    speed_mph = speed_kmh * KMH_TO_MPH

    return raw, speed_kmh, speed_mph


MILESTONES = [
    {
        "target_mph": 18.0,
        "popup_text": "Vehicle reached 18 mph ~ 30kmh",
        "action": None,
        "done": False,
    },
    {
        "target_mph": 37.0,
        "popup_text": "Vehicle reached 37 mph ~ 60kmh - Turn right signal ON",
        "action": send_right_signal,
        "done": False,
    },
    {
        "target_mph": 55.0,
        "popup_text": "Vehicle reached 55 mph ~ 90kmh - Open all doors",
        "action": open_all_doors,
        "done": False,
    },
]


def main():
    global last_speed_raw

    try:
        bus = can.interface.Bus(channel=VCAN, interface="socketcan")
    except Exception as e:
        log(f"[FATAL] Cannot open {VCAN}: {e}")
        return

    log(f"[START] Listening for speed frames on 0x{SPEED_ID:03X}")

    for m in MILESTONES:
        log(f"[INIT] milestone at {m['target_mph']:.1f} mph")

    while True:
        try:
            msg = bus.recv(timeout=0.5)
        except KeyboardInterrupt:
            log("[EXIT] Stopped by user")
            break
        except Exception as e:
            log(f"[ERROR] recv failed: {e}")
            continue

        if msg is None:
            continue

        if msg.arbitration_id != SPEED_ID:
            continue

        raw, speed_kmh, speed_mph = decode_icsim_speed(msg)
        if raw is None:
            continue

        if raw != last_speed_raw:
            log(
                f"[SPEED] raw=0x{raw:04X} | mph={speed_mph:.2f} | kmh={speed_kmh:.2f}"
            )
            last_speed_raw = raw

        for m in MILESTONES:
            if speed_mph < m["target_mph"]:
                m["done"] = False

            if speed_mph >= m["target_mph"] and not m["done"]:
                popup(m["popup_text"])
                log(
                    f"[MILESTONE] reached {m['target_mph']:.1f} mph "
                    f"(mph={speed_mph:.2f} | kmh={speed_kmh:.2f})"
                )

                if m["action"] is not None:
                    m["action"](bus)

                m["done"] = True


if __name__ == "__main__":
    main()