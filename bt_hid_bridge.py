#!/usr/bin/env python3
"""
bt_hid_bridge.py
hci1(00:1A:7D:DA:71:11)을 Bluetooth HID 키보드+마우스로 에뮬레이션.
hci0에 연결된 BT 키보드/마우스 입력을 안드로이드 폰으로 전달.
[Pause] 키로 PC ↔ 폰 모드 토글.

실행: sudo python3 bt_hid_bridge.py
"""

import os
import sys
import socket
import struct
import threading
import time
import logging
import subprocess

from evdev import InputDevice, list_devices, ecodes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── 설정 ─────────────────────────────────────────────────────────────────────
HCI1_ADDR    = "00:1A:7D:DA:71:11"
HID_CTRL_PSM = 17   # HID Control
HID_INTR_PSM = 19   # HID Interrupt
BUS_BLUETOOTH = 5   # evdev bus type

# ── HID 보고서 디스크립터 (키보드 ID=1, 마우스 ID=2) ─────────────────────────
HID_DESCRIPTOR = bytes([
    # Keyboard (Report ID 1)
    0x05, 0x01,              # Usage Page (Generic Desktop)
    0x09, 0x06,              # Usage (Keyboard)
    0xA1, 0x01,              # Collection (Application)
    0x85, 0x01,              #   Report ID 1
    0x05, 0x07,              #   Usage Page (Key Codes)
    0x19, 0xE0,              #   Usage Min (224) — modifier keys
    0x29, 0xE7,              #   Usage Max (231)
    0x15, 0x00,              #   Logical Min (0)
    0x25, 0x01,              #   Logical Max (1)
    0x75, 0x01,              #   Report Size (1)
    0x95, 0x08,              #   Report Count (8)
    0x81, 0x02,              #   Input (Data, Variable, Absolute)
    0x95, 0x01,              #   Report Count (1) — reserved byte
    0x75, 0x08,              #   Report Size (8)
    0x81, 0x03,              #   Input (Constant)
    0x95, 0x06,              #   Report Count (6) — key array
    0x75, 0x08,              #   Report Size (8)
    0x15, 0x00,              #   Logical Min (0)
    0x26, 0xFF, 0x00,        #   Logical Max (255)
    0x05, 0x07,              #   Usage Page (Key Codes)
    0x19, 0x00,              #   Usage Min (0)
    0x29, 0xFF,              #   Usage Max (255)
    0x81, 0x00,              #   Input (Data, Array)
    0xC0,                    # End Collection
    # Mouse (Report ID 2)
    0x05, 0x01,              # Usage Page (Generic Desktop)
    0x09, 0x02,              # Usage (Mouse)
    0xA1, 0x01,              # Collection (Application)
    0x85, 0x02,              #   Report ID 2
    0x09, 0x01,              #   Usage (Pointer)
    0xA1, 0x00,              #   Collection (Physical)
    0x05, 0x09,              #     Usage Page (Buttons)
    0x19, 0x01,              #     Usage Min (1)
    0x29, 0x05,              #     Usage Max (5)
    0x15, 0x00,              #     Logical Min (0)
    0x25, 0x01,              #     Logical Max (1)
    0x95, 0x05,              #     Report Count (5)
    0x75, 0x01,              #     Report Size (1)
    0x81, 0x02,              #     Input (Data, Variable, Absolute)
    0x95, 0x01,              #     Report Count (1) — padding
    0x75, 0x03,              #     Report Size (3)
    0x81, 0x03,              #     Input (Constant)
    0x05, 0x01,              #     Usage Page (Generic Desktop)
    0x09, 0x30,              #     Usage (X)
    0x09, 0x31,              #     Usage (Y)
    0x15, 0x81,              #     Logical Min (-127)
    0x25, 0x7F,              #     Logical Max (127)
    0x75, 0x08,              #     Report Size (8)
    0x95, 0x02,              #     Report Count (2)
    0x81, 0x06,              #     Input (Data, Variable, Relative)
    0x09, 0x38,              #     Usage (Wheel)
    0x15, 0x81,              #     Logical Min (-127)
    0x25, 0x7F,              #     Logical Max (127)
    0x75, 0x08,              #     Report Size (8)
    0x95, 0x01,              #     Report Count (1)
    0x81, 0x06,              #     Input (Data, Variable, Relative)
    0xC0,                    #   End Collection (Physical)
    0xC0,                    # End Collection (Application)
])

# ── modifier 마스크 ───────────────────────────────────────────────────────────
MODIFIER_MAP = {
    ecodes.KEY_LEFTCTRL:  0x01, ecodes.KEY_LEFTSHIFT:  0x02,
    ecodes.KEY_LEFTALT:   0x04, ecodes.KEY_LEFTMETA:   0x08,
    ecodes.KEY_RIGHTCTRL: 0x10, ecodes.KEY_RIGHTSHIFT: 0x20,
    ecodes.KEY_RIGHTALT:  0x40, ecodes.KEY_RIGHTMETA:  0x80,
}

# ── evdev keycode → USB HID keycode ──────────────────────────────────────────
KEYMAP = {
    ecodes.KEY_A: 0x04, ecodes.KEY_B: 0x05, ecodes.KEY_C: 0x06,
    ecodes.KEY_D: 0x07, ecodes.KEY_E: 0x08, ecodes.KEY_F: 0x09,
    ecodes.KEY_G: 0x0A, ecodes.KEY_H: 0x0B, ecodes.KEY_I: 0x0C,
    ecodes.KEY_J: 0x0D, ecodes.KEY_K: 0x0E, ecodes.KEY_L: 0x0F,
    ecodes.KEY_M: 0x10, ecodes.KEY_N: 0x11, ecodes.KEY_O: 0x12,
    ecodes.KEY_P: 0x13, ecodes.KEY_Q: 0x14, ecodes.KEY_R: 0x15,
    ecodes.KEY_S: 0x16, ecodes.KEY_T: 0x17, ecodes.KEY_U: 0x18,
    ecodes.KEY_V: 0x19, ecodes.KEY_W: 0x1A, ecodes.KEY_X: 0x1B,
    ecodes.KEY_Y: 0x1C, ecodes.KEY_Z: 0x1D,
    ecodes.KEY_1: 0x1E, ecodes.KEY_2: 0x1F, ecodes.KEY_3: 0x20,
    ecodes.KEY_4: 0x21, ecodes.KEY_5: 0x22, ecodes.KEY_6: 0x23,
    ecodes.KEY_7: 0x24, ecodes.KEY_8: 0x25, ecodes.KEY_9: 0x26,
    ecodes.KEY_0: 0x27,
    ecodes.KEY_ENTER:      0x28, ecodes.KEY_ESC:        0x29,
    ecodes.KEY_BACKSPACE:  0x2A, ecodes.KEY_TAB:        0x2B,
    ecodes.KEY_SPACE:      0x2C, ecodes.KEY_MINUS:      0x2D,
    ecodes.KEY_EQUAL:      0x2E, ecodes.KEY_LEFTBRACE:  0x2F,
    ecodes.KEY_RIGHTBRACE: 0x30, ecodes.KEY_BACKSLASH:  0x31,
    ecodes.KEY_SEMICOLON:  0x33, ecodes.KEY_APOSTROPHE: 0x34,
    ecodes.KEY_GRAVE:      0x35, ecodes.KEY_COMMA:      0x36,
    ecodes.KEY_DOT:        0x37, ecodes.KEY_SLASH:      0x38,
    ecodes.KEY_CAPSLOCK:   0x39,
    ecodes.KEY_F1:  0x3A, ecodes.KEY_F2:  0x3B, ecodes.KEY_F3:  0x3C,
    ecodes.KEY_F4:  0x3D, ecodes.KEY_F5:  0x3E, ecodes.KEY_F6:  0x3F,
    ecodes.KEY_F7:  0x40, ecodes.KEY_F8:  0x41, ecodes.KEY_F9:  0x42,
    ecodes.KEY_F10: 0x43, ecodes.KEY_F11: 0x44, ecodes.KEY_F12: 0x45,
    ecodes.KEY_SYSRQ:     0x46, ecodes.KEY_SCROLLLOCK: 0x47,
    ecodes.KEY_PAUSE:     0x48,
    ecodes.KEY_INSERT:    0x49, ecodes.KEY_HOME:      0x4A,
    ecodes.KEY_PAGEUP:    0x4B, ecodes.KEY_DELETE:    0x4C,
    ecodes.KEY_END:       0x4D, ecodes.KEY_PAGEDOWN:  0x4E,
    ecodes.KEY_RIGHT:     0x4F, ecodes.KEY_LEFT:      0x50,
    ecodes.KEY_DOWN:      0x51, ecodes.KEY_UP:        0x52,
    ecodes.KEY_NUMLOCK:   0x53,
    ecodes.KEY_KPSLASH:   0x54, ecodes.KEY_KPASTERISK: 0x55,
    ecodes.KEY_KPMINUS:   0x56, ecodes.KEY_KPPLUS:    0x57,
    ecodes.KEY_KPENTER:   0x58,
    ecodes.KEY_KP1: 0x59, ecodes.KEY_KP2: 0x5A, ecodes.KEY_KP3: 0x5B,
    ecodes.KEY_KP4: 0x5C, ecodes.KEY_KP5: 0x5D, ecodes.KEY_KP6: 0x5E,
    ecodes.KEY_KP7: 0x5F, ecodes.KEY_KP8: 0x60, ecodes.KEY_KP9: 0x61,
    ecodes.KEY_KP0: 0x62, ecodes.KEY_KPDOT: 0x63,
}


# ── BT HID 서버 ───────────────────────────────────────────────────────────────
class BTHIDServer:
    def __init__(self):
        self.ctrl_sock = None
        self.intr_sock = None
        self.ctrl_client = None
        self.intr_client = None
        self.connected = threading.Event()
        self._send_lock = threading.Lock()

    def _make_l2cap(self, psm):
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HCI1_ADDR, psm))
        s.listen(1)
        return s

    def wait_for_connection(self):
        """폰 연결 대기 (블로킹). 연결이 끊기면 다시 호출."""
        self.connected.clear()
        if self.ctrl_sock is None:
            self.ctrl_sock = self._make_l2cap(HID_CTRL_PSM)
            self.intr_sock = self._make_l2cap(HID_INTR_PSM)

        log.info("폰에서 블루투스 → 'BT HID Bridge' 연결 대기 중...")
        ctrl_client, addr = self.ctrl_sock.accept()
        log.info(f"Control 연결: {addr[0]}")
        intr_client, _ = self.intr_sock.accept()
        log.info("Interrupt 연결 완료")

        self.ctrl_client = ctrl_client
        self.intr_client = intr_client
        self.connected.set()
        log.info("[연결됨]  Pause 키: PC 모드 ↔ 폰 모드 전환")

        threading.Thread(target=self._ctrl_handler, daemon=True).start()

    def _ctrl_handler(self):
        """HID Control 채널 처리 (GET_DESCRIPTOR 포함)"""
        while self.connected.is_set():
            try:
                data = self.ctrl_client.recv(64)
                if not data:
                    break
                msg_type = (data[0] >> 4) & 0x0F
                param    = data[0] & 0x0F

                if msg_type == 0x04:    # GET_REPORT
                    self.ctrl_client.send(bytes([0xA2, 0x00]))
                elif msg_type == 0x06:  # SET_REPORT → ACK
                    self.ctrl_client.send(bytes([0x00]))
                elif msg_type == 0x08:  # GET_PROTOCOL → Report mode
                    self.ctrl_client.send(bytes([0xA0, 0x01]))
                elif msg_type == 0x03:  # GET_DESCRIPTOR
                    # 디스크립터 타입에 맞게 응답
                    desc = HID_DESCRIPTOR
                    resp = bytes([0xA3]) + struct.pack(">H", len(desc)) + desc
                    self.ctrl_client.send(resp)
                elif msg_type == 0x0E and param == 0x05:  # VIRTUAL_CABLE_UNPLUG
                    break
            except Exception:
                break

        log.info("연결 끊김")
        self.connected.clear()

    def send_keyboard(self, modifier, keys):
        if not self.connected.is_set():
            return
        payload = [0xA1, 0x01, modifier, 0x00] + list(keys)[:6]
        payload += [0x00] * (10 - len(payload))
        self._send(bytes(payload))

    def send_mouse(self, buttons, dx, dy, wheel=0):
        if not self.connected.is_set():
            return
        report = struct.pack("BBBbbb",
            0xA1, 0x02, buttons,
            max(-127, min(127, dx)),
            max(-127, min(127, dy)),
            max(-127, min(127, wheel)),
        )
        self._send(report)

    def _send(self, data):
        with self._send_lock:
            try:
                self.intr_client.send(data)
            except Exception as e:
                log.error(f"전송 오류: {e}")
                self.connected.clear()


# ── 입력 브릿지 ───────────────────────────────────────────────────────────────
class InputBridge:
    def __init__(self, server: BTHIDServer):
        self.server     = server
        self.keyboards  = []
        self.mice       = []
        self.phone_mode = False
        self.modifier   = 0
        self.pressed    = set()   # 현재 눌린 HID 키코드
        self.buttons    = 0       # 마우스 버튼 상태
        self._lock      = threading.Lock()
        # SYN까지 마우스 이동량 누적
        self._dx = self._dy = self._dwheel = 0

    def find_devices(self):
        log.info("BT 입력 장치 검색...")
        for path in list_devices():
            try:
                dev = InputDevice(path)
                if dev.info.bustype != BUS_BLUETOOTH:
                    continue
                caps = dev.capabilities()
                if ecodes.EV_KEY not in caps:
                    continue
                keys = caps[ecodes.EV_KEY]
                if ecodes.KEY_A in keys:
                    log.info(f"  키보드: {dev.name}  ({dev.path})")
                    self.keyboards.append(dev)
                elif ecodes.BTN_LEFT in keys:
                    log.info(f"  마우스: {dev.name}  ({dev.path})")
                    self.mice.append(dev)
            except Exception:
                continue

    def _toggle(self):
        with self._lock:
            self.phone_mode = not self.phone_mode
            if self.phone_mode:
                log.info(">>> [폰 모드]  PC 입력 차단 → 폰으로 전달")
                for d in self.keyboards + self.mice:
                    try: d.grab()
                    except Exception: pass
                # 상태 초기화 및 모든 키 해제 전송
                self.modifier = 0
                self.pressed.clear()
                self.server.send_keyboard(0, [])
                self.server.send_mouse(0, 0, 0)
            else:
                log.info(">>> [PC 모드]  폰 입력 해제 → PC로 전달")
                # 폰에 모든 키 해제 전송 후 grab 해제
                self.server.send_keyboard(0, [])
                self.server.send_mouse(0, 0, 0)
                for d in self.keyboards + self.mice:
                    try: d.ungrab()
                    except Exception: pass

    def _on_key(self, event):
        if event.type != ecodes.EV_KEY:
            return
        key, val = event.code, event.value  # val: 0=up 1=down 2=repeat

        # Pause 키: 어느 모드에서든 토글 (폰으로 전달하지 않음)
        if key == ecodes.KEY_PAUSE and val == 1:
            self._toggle()
            return

        if not self.phone_mode:
            return

        if key in MODIFIER_MAP:
            if val:   self.modifier |= MODIFIER_MAP[key]
            else:     self.modifier &= ~MODIFIER_MAP[key]
        else:
            hid = KEYMAP.get(key, 0)
            if not hid:
                return
            if val:   self.pressed.add(hid)
            else:     self.pressed.discard(hid)

        self.server.send_keyboard(self.modifier, list(self.pressed))

    def _on_mouse(self, event):
        if not self.phone_mode:
            return
        t, c, v = event.type, event.code, event.value

        if t == ecodes.EV_KEY:
            if   c == ecodes.BTN_LEFT:   mask = 0x01
            elif c == ecodes.BTN_RIGHT:  mask = 0x02
            elif c == ecodes.BTN_MIDDLE: mask = 0x04
            else: return
            if v: self.buttons |= mask
            else: self.buttons &= ~mask
            self.server.send_mouse(self.buttons, 0, 0)

        elif t == ecodes.EV_REL:
            if   c == ecodes.REL_X:     self._dx     += v
            elif c == ecodes.REL_Y:     self._dy     += v
            elif c == ecodes.REL_WHEEL: self._dwheel += v

        elif t == ecodes.EV_SYN:
            if self._dx or self._dy or self._dwheel:
                self.server.send_mouse(self.buttons, self._dx, self._dy, self._dwheel)
                self._dx = self._dy = self._dwheel = 0

    def _read_loop(self, dev, handler):
        try:
            for event in dev.read_loop():
                handler(event)
        except Exception as e:
            log.error(f"{dev.name} 읽기 종료: {e}")

    def start(self):
        for dev in self.keyboards:
            threading.Thread(
                target=self._read_loop, args=(dev, self._on_key), daemon=True
            ).start()
        for dev in self.mice:
            threading.Thread(
                target=self._read_loop, args=(dev, self._on_mouse), daemon=True
            ).start()


# ── hci1 초기 설정 ────────────────────────────────────────────────────────────
# PulseAudio가 HSP/HFP 레코드를 재등록할 수 있으므로 매 실행 시 정리 후 HID 등록
AUDIO_SERVICE_CLASSES = {"0x1112", "0x111f", "0x1108", "0x110a", "0x110b"}

def _purge_audio_sdp():
    """로컬 SDP에서 HSP/HFP/A2DP 레코드를 찾아 삭제"""
    result = subprocess.run(["sdptool", "browse", "local"],
                            capture_output=True, text=True)
    handle = None
    remove = False
    for line in result.stdout.splitlines():
        if "RecHandle" in line:
            handle = line.split()[-1]
            remove = False
        elif "Class ID" in line or "UUID" in line:
            lower = line.lower()
            if any(cls in lower for cls in AUDIO_SERVICE_CLASSES) or \
               any(kw in lower for kw in ("headset", "handsfree", "audio gateway",
                                          "a2dp", "avrcp", "0x1108", "0x1112",
                                          "0x111e", "0x111f")):
                remove = True
        elif remove and handle and "RecHandle" in line:
            # 다음 레코드 시작 — 이전 것 삭제
            subprocess.run(["sudo", "sdptool", "del", handle],
                           capture_output=True)
            log.info(f"오디오 SDP 제거: {handle}")
            handle = None
            remove = False
            handle = line.split()[-1]

    if remove and handle:
        subprocess.run(["sudo", "sdptool", "del", handle], capture_output=True)
        log.info(f"오디오 SDP 제거: {handle}")


def setup_hci1():
    cmds = [
        ["hciconfig", "hci1", "up"],
        ["hciconfig", "hci1", "class", "0x002540"],   # Keyboard+Mouse CoD
        ["hciconfig", "hci1", "piscan"],               # discoverable + connectable
        ["hciconfig", "hci1", "name", "BT HID Bridge"],
    ]
    for cmd in cmds:
        subprocess.run(["sudo"] + cmd, check=True, capture_output=True)

    _purge_audio_sdp()

    result = subprocess.run(
        ["sudo", "sdptool", "add", "HID"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log.error(f"sdptool 실패: {result.stderr.strip()}")
        log.error("bluetoothd --compat 미적용 상태입니다. setup.sh를 먼저 실행하세요.")
        sys.exit(1)
    log.info("HID SDP 레코드 등록 완료")


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    if os.geteuid() != 0:
        sys.exit("root 권한 필요:  sudo python3 bt_hid_bridge.py")

    log.info("=== BT HID Bridge 시작 ===")
    setup_hci1()

    server = BTHIDServer()
    bridge = InputBridge(server)
    bridge.find_devices()

    if not bridge.keyboards and not bridge.mice:
        sys.exit("hci0에 BT 키보드/마우스가 연결되어 있지 않습니다")

    bridge.start()

    while True:
        try:
            server.wait_for_connection()
        except KeyboardInterrupt:
            log.info("종료")
            break
        except Exception as e:
            log.error(f"연결 오류: {e}")
            time.sleep(2)
            continue

        # 연결 유지 중 대기
        try:
            while server.connected.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            log.info("종료")
            break

        # 연결 끊기면 폰 모드 해제
        if bridge.phone_mode:
            bridge._toggle()

        log.info("재연결 대기...")


if __name__ == "__main__":
    main()
