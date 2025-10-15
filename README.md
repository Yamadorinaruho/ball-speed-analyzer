# ⚾ 球速測定システム

YOLOv8 + オプティカルフローを使用した自動球速測定システム

## 機能

- ✅ 動画から自動的にボールを検出・追跡
- ✅ キャッチャーミット自動検出によるキャリブレーション不要
- ✅ スローモーション動画の自動補正（8x, 16x対応）
- ✅ オプティカルフローによる高精度トラッキング
- ✅ 詳細なデバッグログ機能

## ローカル実行

### バックエンド
```bash
cd ball-speed-analyzer
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### フロントエンド
```bash
cd frontend
npm install
npm run dev
```

ブラウザで http://localhost:3000 にアクセス

## デプロイ

### Render.com
1. GitHubにリポジトリをプッシュ
2. Render.comでアカウント作成
3. 「New Web Service」から接続
4. 自動デプロイ完了

### Vercel（フロントエンド）
```bash
cd frontend
npm install -g vercel
vercel
```

## 撮影のコツ

- 240fpsのスローモーション撮影を推奨
- 投球→捕球まで撮影（逆再生で自動処理）
- 背景はシンプルに
- 明るい場所で撮影
- カメラは固定

## 技術スタック

- **バックエンド**: FastAPI, YOLOv8, OpenCV, NumPy
- **フロントエンド**: Next.js 15, TailwindCSS, TypeScript
- **AI**: Ultralytics YOLO, Optical Flow (Farneback)

## ライセンス

MIT
