"""
Real-time Fall Detection menggunakan YOLOv8-Pose
=================================================
Jalankan script ini LOKAL di laptop (bukan di Colab), karena butuh akses
langsung ke webcam / RTSP stream CCTV.

Requirement:
    pip install ultralytics opencv-python requests

Cara pakai:
    - Webcam laptop  : VIDEO_SOURCE = 0
    - CCTV/IP Camera : VIDEO_SOURCE = "rtsp://user:pass@192.168.1.10:554/stream1"
"""

import time
import math
from collections import deque

import cv2
import requests
from ultralytics import YOLO

# =========================
# KONFIGURASI
# =========================
MODEL_PATH = "yolov8n-pose.pt"      # model kecil & cepat, cocok untuk real-time
VIDEO_SOURCE = 0                     # ganti ke RTSP URL untuk CCTV
CONF_THRESHOLD = 0.5                 # minimum confidence deteksi orang

# Threshold hasil kalibrasi dari eksperimen video CAUCAFall (lihat notebook eksperimen)
ASPECT_RATIO_THRESHOLD = 0.55        # width/height bbox > ini -> indikasi rebah
TORSO_ANGLE_THRESHOLD = 40           # derajat dari vertikal -> indikasi rebah
VERTICAL_VELOCITY_THRESHOLD = 25     # px/frame turun cepat -> indikasi jatuh (fitur paling reliable)
INACTIVITY_SECONDS = 3               # diam di posisi rebah > ini -> fall confirmed

POSTURE_WINDOW = 7                   # jumlah frame terakhir yang dicek untuk voting
POSTURE_VOTE_RATIO = 0.6             # minimal proporsi frame TRUE dalam window agar dianggap stabil

ALERT_API_URL = "http://127.0.0.1:8000/api/incident-alerts"  # endpoint Laravel

# Index keypoint COCO (dipakai YOLOv8-Pose): 0=hidung,5=bahu kiri,6=bahu kanan,
# 11=pinggul kiri, 12=pinggul kanan, 15=pergelangan kaki kiri, 16=pergelangan kaki kanan
NOSE, L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 0, 5, 6, 11, 12


def calc_torso_angle(shoulder_mid, hip_mid):
    """Sudut kemiringan torso terhadap sumbu vertikal (0 derajat = berdiri tegak)."""
    dx = hip_mid[0] - shoulder_mid[0]
    dy = hip_mid[1] - shoulder_mid[1]
    angle_from_vertical = math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))
    return angle_from_vertical


def calc_aspect_ratio(box):
    x1, y1, x2, y2 = box
    w, h = (x2 - x1), (y2 - y1)
    return w / (h + 1e-6)


def midpoint(p1, p2):
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


class PersonTracker:
    """Menyimpan histori posisi tiap orang (per track id) untuk hitung
    vertical velocity dan durasi tidak bergerak (inactivity)."""

    def __init__(self, history_len=10):
        self.hip_y_history = deque(maxlen=history_len)
        self.posture_flags = deque(maxlen=POSTURE_WINDOW)  # history True/False tiap frame
        self.fall_suspected_since = None
        self.last_hip_pos = None
        self.alert_sent = False

    def update_posture_flag(self, is_fall_posture):
        """Catat hasil deteksi per-frame, lalu putuskan status STABIL berdasarkan
        voting mayoritas beberapa frame terakhir -> tahan terhadap noise/flicker
        keypoint saat orang sedang tergeletak."""
        self.posture_flags.append(is_fall_posture)
        if len(self.posture_flags) < self.posture_flags.maxlen:
            return False  # belum cukup data, anggap belum stabil
        true_ratio = sum(self.posture_flags) / len(self.posture_flags)
        return true_ratio >= POSTURE_VOTE_RATIO

    def update_hip(self, hip_mid):
        self.hip_y_history.append(hip_mid[1])
        self.last_hip_pos = hip_mid

    def vertical_velocity(self):
        if len(self.hip_y_history) < 2:
            return 0
        return self.hip_y_history[-1] - self.hip_y_history[0]

    def is_inactive(self, current_hip, movement_threshold=15):
        if self.last_hip_pos is None:
            return False
        dist = math.dist(current_hip, self.last_hip_pos)
        return dist < movement_threshold


def send_alert(frame, track_id, confidence):
    """Kirim event alert + snapshot ke backend Laravel."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    filename = f"alert_{track_id}_{int(time.time())}.jpg"
    cv2.imwrite(filename, frame)

    payload = {
        "status": "fall_detected",
        "timestamp": timestamp,
        "confidence": round(confidence, 2),
        "device_id": 1,  # sesuaikan dengan id device yang sudah kamu buat di tabel `devices`
    }
    try:
        with open(filename, "rb") as img_file:
            requests.post(
                ALERT_API_URL,
                data=payload,
                files={"thumbnail": img_file},
                timeout=3,
            )
        print(f"[ALERT SENT] {payload}")
    except requests.exceptions.RequestException as e:
        print(f"[WARNING] Gagal kirim alert ke backend: {e}")


def main():
    model = YOLO(MODEL_PATH)
    cap = cv2.VideoCapture(VIDEO_SOURCE)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # kurangi lag pada RTSP stream

    trackers = {}  # track_id -> PersonTracker

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("Gagal membaca frame, mencoba lagi...")
            continue

        results = model.track(frame, persist=True, conf=CONF_THRESHOLD, verbose=False)
        annotated_frame = results[0].plot()

        if results[0].boxes.id is not None and results[0].keypoints is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            keypoints = results[0].keypoints.xy.cpu().numpy()

            for box, track_id, kpts in zip(boxes, track_ids, keypoints):
                if track_id not in trackers:
                    trackers[track_id] = PersonTracker()
                tracker = trackers[track_id]

                shoulder_mid = midpoint(kpts[L_SHOULDER], kpts[R_SHOULDER])
                hip_mid = midpoint(kpts[L_HIP], kpts[R_HIP])

                aspect_ratio = calc_aspect_ratio(box)
                torso_angle = calc_torso_angle(shoulder_mid, hip_mid)

                tracker.update_hip(hip_mid)
                v_velocity = tracker.vertical_velocity()

                # --- Heuristic & Motion Analysis (per-frame) ---
                raw_posture_flag = (
                    aspect_ratio > ASPECT_RATIO_THRESHOLD
                    or torso_angle > TORSO_ANGLE_THRESHOLD
                    or v_velocity > VERTICAL_VELOCITY_THRESHOLD
                )
                # Stabilkan lewat voting mayoritas beberapa frame terakhir,
                # supaya 1 frame noise (mis. keypoint salah baca saat rebah)
                # tidak langsung mereset status yang sedang dipantau.
                posture_indicates_fall = tracker.update_posture_flag(raw_posture_flag)

                status_text = "Normal"
                if posture_indicates_fall:
                    status_text = "Suspected Fall"
                    if tracker.fall_suspected_since is None:
                        tracker.fall_suspected_since = time.time()

                    duration = time.time() - tracker.fall_suspected_since
                    inactive = tracker.is_inactive(hip_mid)

                    # --- Fall Confirmation & Thresholding ---
                    if duration >= INACTIVITY_SECONDS and inactive and not tracker.alert_sent:
                        status_text = "FALL DETECTED"
                        send_alert(frame, track_id, confidence=0.9)
                        tracker.alert_sent = True
                else:
                    tracker.fall_suspected_since = None
                    tracker.alert_sent = False

                x1, y1 = int(box[0]), int(box[1])
                color = (0, 0, 255) if "FALL" in status_text else (0, 255, 0)
                cv2.putText(
                    annotated_frame, f"ID {track_id}: {status_text}",
                    (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
                )

        cv2.imshow("Fall Detection - press 'q' to quit", annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
