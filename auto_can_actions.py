import can
import subprocess
import time
from datetime import datetime

VCAN = "vcan0"

# CAN IDs
SPEED_ID = 0x3EA
SIGNAL_ID = 0x47D
DOOR_ID = 0x474

# Thresholds: yêu cầu assignment theo km/h, nhưng dashboard / speed byte là MPH
THRESHOLD_30_KMH_MPH = 19   # ~ 30 km/h
THRESHOLD_60_KMH_MPH = 37   # ~ 60 km/h
THRESHOLD_90_KMH_MPH = 56   # ~ 90 km/h

# Trigger flags để tránh gửi lặp liên tục khi speed frame lặp periodic
done_30 = False
done_60 = False
done_90 = False


def now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(message: str) -> None:
    print(f"[{now_str()}] {message}", flush=True)


def popup(message: str) -> None:
    subprocess.run(["notify-send", message], check=False)


def format_cansend(can_id: int, data: bytes) -> str:
    return f"cansend {VCAN} {can_id:03X}#{data.hex().upper()}"


def send_can_frame(bus: can.Bus, can_id: int, data: bytes, action_desc: str, repeat: int = 3, delay: float = 0.05) -> None:
    cmd_str = format_cansend(can_id, data)

    log(f"[TX-REQUEST] {action_desc}")
    log(f"[TX-CMD] {cmd_str}")

    try:
        msg = can.Message(
            arbitration_id=can_id,
            data=data,
            is_extended_id=False
        )

        for i in range(repeat):
            bus.send(msg)
            log(f"[TX-SENT] ({i+1}/{repeat}) {cmd_str}")
            time.sleep(delay)

        log(f"[TX-OK] Completed: {action_desc}")

    except can.CanError as e:
        log(f"[TX-ERROR] Failed to send frame: {cmd_str}")
        log(f"[TX-ERROR] Reason: {e}")


def send_right_signal(bus: can.Bus) -> None:
    # 47D#000000000002
    data = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x02])
    send_can_frame(
        bus=bus,
        can_id=SIGNAL_ID,
        data=data,
        action_desc="Turn RIGHT signal ON"
    )


def open_all_doors(bus: can.Bus) -> None:
    # 474#00
    data = bytes([0x00])
    send_can_frame(
        bus=bus,
        can_id=DOOR_ID,
        data=data,
        action_desc="Open ALL doors"
    )


def main() -> None:
    global done_30, done_60, done_90

    log("[INIT] Starting auto CAN action script...")
    log(f"[INIT] Interface: {VCAN}")
    log(f"[INIT] SPEED_ID = 0x{SPEED_ID:03X}")
    log(f"[INIT] SIGNAL_ID = 0x{SIGNAL_ID:03X}")
    log(f"[INIT] DOOR_ID = 0x{DOOR_ID:03X}")
    log("[INIT] Thresholds:")
    log(f"       30 km/h  -> {THRESHOLD_30_KMH_MPH} mph")
    log(f"       60 km/h  -> {THRESHOLD_60_KMH_MPH} mph")
    log(f"       90 km/h  -> {THRESHOLD_90_KMH_MPH} mph")

    try:
        bus = can.interface.Bus(channel=VCAN, interface="socketcan")
    except Exception as e:
        log(f"[FATAL] Cannot open CAN interface {VCAN}: {e}")
        return

    log("[LISTEN] Waiting for speed frames on 0x3EA ...")

    while True:
        try:
            msg = bus.recv()
        except KeyboardInterrupt:
            log("[EXIT] Stopped by user.")
            break
        except Exception as e:
            log(f"[RX-ERROR] bus.recv() failed: {e}")
            continue

        if msg is None:
            continue

        if msg.arbitration_id != SPEED_ID:
            continue

        if len(msg.data) != 7:
            log(f"[RX-WARN] Unexpected DLC for 0x3EA: {len(msg.data)} (expected 7)")
            continue

        speed_mph = msg.data[6]
        speed_kmh = speed_mph * 1.60934

        log(f"[SPEED] {speed_mph:>3} mph | {speed_kmh:>6.1f} km/h | raw frame: 3EA#{msg.data.hex().upper()}")

        # reset trigger khi tốc độ tụt xuống dưới ngưỡng
        if speed_mph < THRESHOLD_30_KMH_MPH and done_30:
            log("[RESET] Speed dropped below 30 km/h threshold -> re-arm milestone 30")
            done_30 = False

        if speed_mph < THRESHOLD_60_KMH_MPH and done_60:
            log("[RESET] Speed dropped below 60 km/h threshold -> re-arm milestone 60")
            done_60 = False

        if speed_mph < THRESHOLD_90_KMH_MPH and done_90:
            log("[RESET] Speed dropped below 90 km/h threshold -> re-arm milestone 90")
            done_90 = False

        # Milestone 30 km/h
        if speed_mph >= THRESHOLD_30_KMH_MPH and not done_30:
            log("[MILESTONE] Reached 30 km/h threshold (~19 mph)")
            popup("Vehicle reaches 30 km/h")
            log("[POPUP] Vehicle reaches 30 km/h")
            done_30 = True

        # Milestone 60 km/h
        if speed_mph >= THRESHOLD_60_KMH_MPH and not done_60:
            log("[MILESTONE] Reached 60 km/h threshold (~37 mph)")
            popup("Vehicle reaches 60 km/h - Turn right signal ON")
            log("[POPUP] Vehicle reaches 60 km/h - Turn right signal ON")
            send_right_signal(bus)
            done_60 = True

        # Milestone 90 km/h
        if speed_mph >= THRESHOLD_90_KMH_MPH and not done_90:
            log("[MILESTONE] Reached 90 km/h threshold (~56 mph)")
            popup("Vehicle reaches 90 km/h - Open all doors")
            log("[POPUP] Vehicle reaches 90 km/h - Open all doors")
            open_all_doors(bus)
            done_90 = True


if __name__ == "__main__":
    main()