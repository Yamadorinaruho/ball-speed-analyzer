from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import cv2
import numpy as np
from ultralytics import YOLO
import tempfile
import os
from pathlib import Path
import math
import torch
from ultralytics.nn.tasks import DetectionModel

# PyTorch 2.6のweights_only対策
torch.serialization.add_safe_globals([DetectionModel])

app = FastAPI()
# CORS設定
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# YOLOv8モデルのロード
model = YOLO('yolov8n.pt')

# キャッチャーミットの標準サイズ（メートル）
MITT_SIZE_M = 0.32  # 32cm

class BallTracker:
    def __init__(self):
        self.tracks = {}
        self.next_id = 0
        self.max_distance = 150
        self.prev_gray = None

    def update(self, detections, frame_idx, frame=None):
        """簡易的なトラッキング + オプティカルフロー補完"""

        # オプティカルフローで既存トラックを予測
        if frame is not None and self.prev_gray is not None and len(self.tracks) > 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # オプティカルフロー計算
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray, gray, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )

            # 既存トラックの位置を予測
            for track_id, track_data in self.tracks.items():
                if track_data['last_seen'] == frame_idx - 1:
                    last_x, last_y, _ = track_data['positions'][-1]
                    x, y = int(last_x), int(last_y)
                    if 0 <= y < flow.shape[0] and 0 <= x < flow.shape[1]:
                        dx, dy = flow[y, x]
                        track_data['predicted'] = (last_x + dx, last_y + dy)

            self.prev_gray = gray
        elif frame is not None:
            self.prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if len(detections) == 0:
            return []

        current_centers = []
        for det in detections:
            x1, y1, x2, y2 = det[:4]
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            current_centers.append([cx, cy, det])

        if len(self.tracks) == 0:
            for cx, cy, det in current_centers:
                self.tracks[self.next_id] = {
                    'positions': [(cx, cy, frame_idx)],
                    'last_seen': frame_idx
                }
                self.next_id += 1
        else:
            matched = set()
            for cx, cy, det in current_centers:
                best_id = None
                best_dist = self.max_distance

                for track_id, track_data in self.tracks.items():
                    if track_id in matched:
                        continue

                    # 予測位置がある場合はそれを使用、なければ最後の位置
                    if 'predicted' in track_data and track_data['last_seen'] == frame_idx - 1:
                        pred_x, pred_y = track_data['predicted']
                        dist = math.sqrt((cx - pred_x)**2 + (cy - pred_y)**2)
                    else:
                        last_pos = track_data['positions'][-1]
                        dist = math.sqrt((cx - last_pos[0])**2 + (cy - last_pos[1])**2)

                    if dist < best_dist:
                        best_dist = dist
                        best_id = track_id

                if best_id is not None:
                    self.tracks[best_id]['positions'].append((cx, cy, frame_idx))
                    self.tracks[best_id]['last_seen'] = frame_idx
                    if 'predicted' in self.tracks[best_id]:
                        del self.tracks[best_id]['predicted']
                    matched.add(best_id)
                else:
                    self.tracks[self.next_id] = {
                        'positions': [(cx, cy, frame_idx)],
                        'last_seen': frame_idx
                    }
                    self.next_id += 1

        return self.tracks

def detect_mitt_and_calculate_scale(cap, model):
    """
    動画からキャッチャーミットを検出してスケールを計算
    baseball glove (class_id=36)を検出
    """
    mitt_sizes = []
    frame_count = 0
    max_frames_to_check = 60  # 最初の60フレームをチェック
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    
    while frame_count < max_frames_to_check:
        ret, frame = cap.read()
        if not ret:
            break
        
        # グローブを検出 (class_id=36: baseball glove)
        results = model(frame, classes=[36], conf=0.4, verbose=False)
        
        if len(results[0].boxes) > 0:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            
            for box in boxes:
                x1, y1, x2, y2 = box
                # ミットの縦サイズ（ピクセル）
                height = y2 - y1
                width = x2 - x1
                
                # 縦長ならキャッチャーミットの可能性が高い
                if height > 50 and height > width * 0.7:
                    mitt_sizes.append(height)
        
        frame_count += 1
    
    # ミットが検出されなかった場合
    if len(mitt_sizes) == 0:
        return None
    
    # 中央値を使用（外れ値に強い）
    median_mitt_size_pixels = np.median(mitt_sizes)
    
    # ピクセルからメートルへの変換係数を計算
    # pixel_to_meter = 実際のサイズ(m) / ピクセルサイズ
    pixel_to_meter = MITT_SIZE_M / median_mitt_size_pixels
    
    return pixel_to_meter

def calculate_speed(positions, fps, pixel_to_meter):
    """
    位置情報から速度を計算
    移動速度が最も速い区間を使用（投球の瞬間を検出）
    """
    if len(positions) < 5:
        return None

    # 各フレーム間の移動速度を計算
    speeds = []
    for i in range(len(positions) - 1):
        x1, y1, f1 = positions[i]
        x2, y2, f2 = positions[i + 1]

        # フレーム間の距離（ピクセル）
        pixel_dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

        # 時間（秒）
        time_diff = (f2 - f1) / fps

        if time_diff > 0:
            # 速度 (m/s)
            speed_ms = (pixel_dist * pixel_to_meter) / time_diff
            speeds.append((i, speed_ms))

    if len(speeds) == 0:
        return None

    # 極端に遅い速度（静止状態）を除外
    # 上位75%以上の速度のみを使用（下位25%を除外）
    all_speeds = [s[1] for s in speeds]
    sorted_speeds = sorted(all_speeds, reverse=True)

    # 上位75%を使用
    top_75_count = max(1, int(len(sorted_speeds) * 0.75))
    threshold = sorted_speeds[top_75_count - 1] if top_75_count <= len(sorted_speeds) else 0

    filtered_speeds = [s for s in speeds if s[1] >= threshold]

    if len(filtered_speeds) == 0:
        filtered_speeds = speeds  # フィルタしすぎた場合は元に戻す

    # さらに上位50%の平均を取る（最も速い区間）
    filtered_speeds.sort(key=lambda x: x[1], reverse=True)
    top_50_percent = max(1, len(filtered_speeds) // 2)
    top_speeds = [s[1] for s in filtered_speeds[:top_50_percent]]

    avg_speed_ms = np.mean(top_speeds)
    speed_kmh = avg_speed_ms * 3.6

    print(f"速度計算: 全{len(speeds)}区間 → フィルタ後{len(filtered_speeds)}区間 → 上位{len(top_speeds)}区間の平均")
    print(f"速度範囲: 最小{min(all_speeds)*3.6:.1f} - 中央{np.median(all_speeds)*3.6:.1f} - 最大{max(all_speeds)*3.6:.1f} km/h")

    return speed_kmh

@app.post("/api/analyze")
async def analyze_video(file: UploadFile = File(...)):
    """動画をアップロードして球速を分析"""

    if not file.filename.endswith(('.mp4', '.mov', '.avi')):
        raise HTTPException(status_code=400, detail="動画ファイルをアップロードしてください")

    # 一時ファイルに保存
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # 動画を開く
        cap = cv2.VideoCapture(tmp_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # スローモーション補正
        # 通常、プロ野球の投球は約0.4-0.5秒でホームに到達
        # 動画の長さから実際の撮影速度を推定
        video_duration = total_frames / fps

        # スローモーション動画の判定と補正
        # 一般的なスローモーション：240fps撮影→30fps再生 = 8倍スロー
        # つまり、動画で4.8秒 = 実時間0.6秒
        if fps <= 60 and video_duration > 2.0:
            # スローモーション動画と判定
            # 実際の撮影FPSを推定（一般的な値: 120, 240, 480fps）
            # 動画の長さから逆算
            estimated_real_duration = 0.5  # 投球の実時間（秒）
            recording_fps_multiplier = video_duration / estimated_real_duration

            # 一般的なスローモーション倍率に丸める (2x, 4x, 8x, 16x)
            if recording_fps_multiplier > 12:
                slowmo_factor = 16.0
            elif recording_fps_multiplier > 6:
                slowmo_factor = 8.0
            elif recording_fps_multiplier > 3:
                slowmo_factor = 4.0
            elif recording_fps_multiplier > 1.5:
                slowmo_factor = 2.0
            else:
                slowmo_factor = 1.0

            print(f"スローモーション検出: {slowmo_factor:.1f}x (FPS={fps}, 動画時間={video_duration:.1f}s, 推定倍率={recording_fps_multiplier:.1f}x)")
        else:
            slowmo_factor = 1.0
            print(f"通常速度と判定 (FPS={fps}, 動画時間={video_duration:.1f}s)")

        # 全フレームを読み込んで逆順にする
        print(f"動画読み込み中... (合計 {total_frames} フレーム)")
        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
        cap.release()

        # 逆再生（捕球→投球の順に処理）
        frames.reverse()
        print(f"動画を逆再生モードに変換しました")

        # ステップ1: キャッチャーミットを検出してスケールを計算
        print("キャッチャーミット検出中...")
        mitt_sizes = []
        for i, frame in enumerate(frames[:60]):  # 最初の60フレーム（逆再生なので捕球シーン）
            results = model(frame, classes=[36], conf=0.2, verbose=False)
            if len(results[0].boxes) > 0:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                for box in boxes:
                    x1, y1, x2, y2 = box
                    height = y2 - y1
                    width = x2 - x1
                    # ミットのサイズチェック: 画面の5-30%程度の高さ
                    frame_height = frames[0].shape[0]
                    size_ratio = height / frame_height
                    # 縦長で適切なサイズのものだけを採用
                    if (height > 50 and height < frame_height * 0.5 and
                        height > width * 0.7 and
                        0.05 < size_ratio < 0.3):
                        mitt_sizes.append(height)

        mitt_detected = len(mitt_sizes) > 3  # 最低4回検出されること
        if mitt_detected:
            median_mitt_size = np.median(mitt_sizes)
            pixel_to_meter = MITT_SIZE_M / median_mitt_size

            # 異常値チェック: 妥当な範囲かどうか
            if 0.001 < pixel_to_meter < 0.1:
                print(f"ミット検出成功: スケール = {pixel_to_meter:.6f} m/pixel (ミットサイズ={median_mitt_size:.1f}px)")
            else:
                print(f"ミット検出失敗: スケール値が異常 ({pixel_to_meter:.6f})")
                mitt_detected = False

        if not mitt_detected:
            # ミット未検出時は動画解像度から推定
            # 一般的な野球動画の撮影距離を推定
            height, width = frames[0].shape[:2]

            # 画面に映る実際の範囲を推定
            # 縦長動画（スマホ撮影）の場合、ズームして撮影している可能性が高い
            # ボールの実サイズ（約7.3cm）とピクセルサイズから推定する方が精度が高い
            # 代わりに、一般的な撮影距離（約15m）での画角を使用
            if height > width:
                # 縦長動画：画面幅に約10-12mの範囲が映っていると仮定
                estimated_field_width = 11.0  # メートル
                coverage_ratio = 1.0
            else:
                # 横長動画：より広い範囲を撮影
                estimated_field_width = 18.0
                coverage_ratio = 0.7

            pixel_to_meter = estimated_field_width / (width * coverage_ratio)
            print(f"ミット未検出: 解像度ベース推定値を使用 ({width}x{height}px → {pixel_to_meter:.6f} m/pixel, 画面幅={estimated_field_width}m)")

        # ステップ2: ボールをトラッキング
        tracker = BallTracker()
        frame_idx = 0
        detection_count = 0

        print("ボール追跡中（オプティカルフロー有効）...")
        for frame in frames:
            # YOLOで検出（sports ballクラス: class_id=32、baseballクラス: class_id=37）
            # 信頼度を大幅に下げて検出力を最大化
            results = model(frame, classes=[32, 37], conf=0.01, verbose=False)

            detections = []
            if len(results[0].boxes) > 0:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                confs = results[0].boxes.conf.cpu().numpy()

                for box, conf in zip(boxes, confs):
                    # ボールのサイズフィルタ（小さすぎる/大きすぎる検出を除外）
                    width = box[2] - box[0]
                    height = box[3] - box[1]
                    if 5 < width < 200 and 5 < height < 200:
                        detections.append([*box, conf])
                        detection_count += 1

            # オプティカルフローを使用したトラッキング
            tracker.update(detections, frame_idx, frame=frame)
            frame_idx += 1

        print(f"ボール検出回数: {detection_count} 回")
        print(f"検出されたトラック数: {len(tracker.tracks)}")
        
        # 最も長いトラックを選択（ただし、動きがあるものに限定）
        best_track = None
        max_length = 0

        for track_id, track_data in tracker.tracks.items():
            positions = track_data['positions']
            if len(positions) < 5:
                continue

            # トラックの移動距離をチェック
            start_x, start_y, _ = positions[0]
            end_x, end_y, _ = positions[-1]
            total_dist = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)

            # 最低10ピクセル以上動いているトラックのみ採用
            # かつ、最大150フレームまでに制限（長すぎる追跡は静止オブジェクト）
            if (total_dist > 10 and
                len(positions) > max_length and
                len(positions) <= 150):
                max_length = len(positions)
                best_track = track_data

        print(f"最良トラック: {max_length}フレーム")
        
        if best_track is None or max_length < 5:
            return JSONResponse({
                "success": False,
                "message": f"ボールを検出できませんでした（検出回数: {detection_count}回、最長トラック: {max_length}フレーム）。明るい場所で背景をシンプルにして撮影してください。",
                "fps": fps,
                "total_frames": total_frames,
                "mitt_detected": mitt_detected,
                "detection_count": detection_count,
                "max_track_length": max_length
            })
        
        # 球速計算（スローモーション補正を適用）
        speed = calculate_speed(best_track['positions'], fps, pixel_to_meter)

        if speed is not None:
            speed = speed * slowmo_factor  # スローモーション補正
            print(f"補正前速度 → 補正後速度: {speed/slowmo_factor:.1f} → {speed:.1f} km/h")

        if speed is None:
            return JSONResponse({
                "success": False,
                "message": "球速を計算できませんでした",
                "detected_frames": max_length,
                "fps": fps,
                "mitt_detected": mitt_detected
            })
        
        # 異常値チェック（野球の球速として妥当な範囲）
        if speed < 10 or speed > 200:
            warning = "計測値が異常です。ミットが正しく検出されていない可能性があります。"
        else:
            warning = None
        
        return JSONResponse({
            "success": True,
            "speed_kmh": round(speed, 1),
            "speed_mph": round(speed * 0.621371, 1),
            "detected_frames": max_length,
            "fps": fps,
            "total_frames": total_frames,
            "tracking_duration_ms": round((max_length / fps) * 1000, 1),
            "mitt_detected": mitt_detected,
            "calibration_method": "キャッチャーミット自動検出" if mitt_detected else "推定値",
            "scale_factor": round(pixel_to_meter, 6),
            "slowmo_factor": round(slowmo_factor, 1),
            "warning": warning
        })
        
    finally:
        # 一時ファイル削除
        os.unlink(tmp_path)

@app.get("/")
async def root():
    return {"message": "Ball Speed Analyzer API - Auto Calibration with Mitt Detection"}

@app.get("/health")
async def health():
    return {"status": "ok"}

# 実行方法:
# pip install fastapi uvicorn opencv-python numpy ultralytics python-multipart
# uvicorn main:app --reload --host 0.0.0.0 --port 8000