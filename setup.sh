#!/bin/bash
# setup.sh - Ubuntu PC에서 최초 1회 실행
set -e

echo "=== 1단계: 패키지 설치 ==="
sudo apt-get install -y python3-evdev bluez bluez-tools

echo ""
echo "=== 2단계: bluetoothd --compat 활성화 (sdptool 사용을 위해 필요) ==="
OVERRIDE_DIR="/etc/systemd/system/bluetooth.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/compat.conf"

if ! grep -q "\-\-compat" /lib/systemd/system/bluetooth.service 2>/dev/null &&
   ! [ -f "$OVERRIDE_FILE" ]; then
    sudo mkdir -p "$OVERRIDE_DIR"
    sudo tee "$OVERRIDE_FILE" > /dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/libexec/bluetooth/bluetoothd --compat
EOF
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    echo "bluetoothd --compat 적용 완료"
else
    echo "이미 설정되어 있거나 불필요"
fi

echo ""
echo "=== 3단계: hci1 초기 설정 ==="
sudo hciconfig hci1 up
sudo hciconfig hci1 class 0x002540
sudo hciconfig hci1 piscan
sudo hciconfig hci1 name "BT HID Bridge"

echo ""
echo "=== 4단계: 폰과 페어링 (최초 1회) ==="
echo ""
echo "  bluetoothctl 을 실행하고 아래 순서대로 입력하세요:"
echo ""
echo "    select 00:1A:7D:DA:71:11"
echo "    agent on"
echo "    default-agent"
echo "    discoverable on"
echo "    pairable on"
echo ""
echo "  그 다음 폰에서: 설정 → 블루투스 → 새 기기 검색 → 'BT HID Bridge' 선택 → 페어링"
echo ""
echo "  페어링 완료 후 bluetoothctl 에서:"
echo "    trust <폰의 MAC 주소>"
echo "    quit"
echo ""
echo "=== 5단계: 브릿지 실행 ==="
echo "  sudo python3 bt_hid_bridge.py"
echo ""
echo "  [사용법]"
echo "  - 기본: PC 키보드/마우스 정상 동작"
echo "  - Pause 키: 폰 모드 전환 (PC 입력 차단, 폰 제어)"
echo "  - Pause 키 다시: PC 모드 복귀"
