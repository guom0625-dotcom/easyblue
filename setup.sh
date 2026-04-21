#!/bin/bash
# setup.sh - Ubuntu PC에서 최초 1회 실행
set -e

echo "=== 1단계: 패키지 설치 ==="
sudo apt-get install -y python3-evdev bluez bluez-tools

echo ""
echo "=== 2단계: bluetoothd --compat 활성화 (sdptool 사용을 위해 필요) ==="
OVERRIDE_DIR="/etc/systemd/system/bluetooth.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/compat.conf"

# 실제 적용된 ExecStart 확인 (override 포함)
BT_EXEC=$(systemctl cat bluetooth 2>/dev/null | grep "^ExecStart=" | tail -1)
echo "현재 ExecStart: $BT_EXEC"

if echo "$BT_EXEC" | grep -q "\-\-compat"; then
    echo "이미 --compat 적용됨"
else
    sudo mkdir -p "$OVERRIDE_DIR"
    # bluetoothd 경로 자동 탐지
    BT_BIN=$(systemctl cat bluetooth 2>/dev/null | grep "^ExecStart=" | tail -1 | awk '{print $1}' | sed 's/ExecStart=//')
    [ -z "$BT_BIN" ] && BT_BIN=$(which bluetoothd 2>/dev/null || echo "/usr/libexec/bluetooth/bluetoothd")
    echo "bluetoothd 경로: $BT_BIN"
    sudo tee "$OVERRIDE_FILE" > /dev/null <<EOF
[Service]
ExecStart=
ExecStart=$BT_BIN --compat
EOF
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    sleep 2
    echo "bluetoothd --compat 적용 완료"
fi

echo ""
echo "=== 3-1단계: PulseAudio HSP 프로파일 비활성화 ==="
# PulseAudio가 BlueZ에 HSP/HFP를 등록하지 않도록 설정
PA_CONF="$HOME/.config/pulse/default.pa"
mkdir -p "$HOME/.config/pulse"
if [ ! -f "$PA_CONF" ] || ! grep -q "bluetooth-discover" "$PA_CONF"; then
    # 시스템 기본값 복사 후 headset=ofono(없으면 비활성) 설정
    cp /etc/pulse/default.pa "$PA_CONF" 2>/dev/null || cat > "$PA_CONF" <<'PAEOF'
.include /etc/pulse/default.pa
PAEOF
    # headset 역할 제거: module-bluetooth-discover에서 headset 파라미터 추가
    if grep -q "module-bluetooth-discover" "$PA_CONF"; then
        sed -i 's/load-module module-bluetooth-discover$/load-module module-bluetooth-discover headset=ofono/' "$PA_CONF"
    else
        echo "load-module module-bluetooth-discover headset=ofono" >> "$PA_CONF"
    fi
    echo "PulseAudio bluetooth headset 비활성화 설정 완료"
    echo "변경 적용: pulseaudio -k && pulseaudio --start"
    pulseaudio -k 2>/dev/null; sleep 1; pulseaudio --start 2>/dev/null || true
else
    echo "이미 설정됨"
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
