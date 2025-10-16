'use client';

import { useState } from 'react';

// APIレスポンスの型定義
interface AnalysisResult {
  success: boolean;
  speed_kmh?: number;
  speed_mph?: number;
  detected_frames?: number;
  fps?: number;
  total_frames?: number;
  tracking_duration_ms?: number;
  mitt_detected?: boolean;
  calibration_method?: string;
  scale_factor?: number;
  slowmo_factor?: number;
  warning?: string | null;
  message?: string;
}

// エラー詳細の型定義（anyを削除）
interface ErrorDetails {
  name?: string;
  message?: string;
  type?: string;
  [key: string]: unknown;  // anyの代わりにunknownを使用
}

export default function BallSpeedAnalyzer() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<ErrorDetails | null>(null);
  const [dragActive, setDragActive] = useState<boolean>(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setResult(null);
      setError(null);
    }
  };

  const handleDrag = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
      setResult(null);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError('ファイルを選択してください');
      return;
    }

    setLoading(true);
    setError(null);
    setErrorDetails(null);
    setResult(null);

    console.log('=== 球速測定開始 ===');
    console.log('ファイル名:', file.name);
    console.log('ファイルサイズ:', (file.size / 1024 / 1024).toFixed(2), 'MB');
    console.log('ファイルタイプ:', file.type);
    console.log('アップロード時刻:', new Date().toISOString());

    const formData = new FormData();
    formData.append('file', file);

    const startTime = performance.now();

    try {
      console.log('APIリクエスト送信中...');
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
      const response = await fetch(`${apiUrl}/api/analyze`, {
        method: 'POST',
        body: formData,
      });

      const requestTime = performance.now() - startTime;
      console.log('APIレスポンス受信:', requestTime.toFixed(0), 'ms');
      console.log('HTTPステータス:', response.status, response.statusText);

      const data: AnalysisResult = await response.json();
      console.log('=== APIレスポンスデータ ===');
      console.log(JSON.stringify(data, null, 2));

      if (data.success) {
        console.log('✅ 測定成功!');
        console.log('球速:', data.speed_kmh, 'km/h');
        console.log('検出フレーム数:', data.detected_frames);
        console.log('FPS:', data.fps);
        console.log('スローモーション係数:', data.slowmo_factor);
        console.log('スケール係数:', data.scale_factor);
        console.log('ミット検出:', data.mitt_detected ? '成功' : '失敗');
        setResult(data);
      } else {
        console.error('❌ 測定失敗:', data.message);
        console.log('失敗詳細:', data);
        setError(data.message || '分析に失敗しました');
        setErrorDetails({
          message: data.message,
          type: 'api_error',
          ...data
        } as ErrorDetails);
      }
    } catch (err) {
      const error = err as Error;
      console.error('❌ ネットワークエラー:', error);
      console.error('エラー詳細:', {
        name: error.name,
        message: error.message,
        stack: error.stack
      });
      setError('サーバーに接続できませんでした。FastAPIが起動しているか確認してください。');
      setErrorDetails({
        name: error.name,
        message: error.message,
        type: 'network_error'
      });
    } finally {
      const totalTime = performance.now() - startTime;
      console.log('=== 処理完了 ===');
      console.log('合計処理時間:', totalTime.toFixed(0), 'ms');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">⚾ 球速測定システム</h1>
          <p className="text-gray-600">YOLOv11 + ミット自動検出</p>
          <p className="text-sm text-blue-600 mt-1">✨ キャリブレーション不要</p>
        </div>

        <div className="bg-white rounded-lg shadow-xl p-8">
          <div
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
              dragActive
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-300 hover:border-gray-400'
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              className="hidden"
              id="video-upload"
            />
            <label htmlFor="video-upload" className="cursor-pointer">
              <div className="text-6xl mb-4">🎥</div>
              <p className="text-lg font-semibold text-gray-700 mb-2">
                動画をドラッグ&ドロップ
              </p>
              <p className="text-sm text-gray-500 mb-4">
                または クリックしてファイルを選択
              </p>
              <p className="text-xs text-gray-400">
                対応形式: MP4, MOV, AVI
              </p>
            </label>
          </div>

          {file && (
            <div className="mt-6 p-4 bg-gray-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-2">選択されたファイル:</p>
              <p className="font-semibold text-gray-800">{file.name}</p>
              <p className="text-xs text-gray-500 mt-1">
                サイズ: {(file.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
          )}

          <button
            onClick={handleUpload}
            disabled={!file || loading}
            className={`w-full mt-6 py-4 rounded-lg font-bold text-white text-lg transition-all ${
              !file || loading
                ? 'bg-gray-300 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700 active:scale-95'
            }`}
          >
            {loading ? (
              <span className="flex items-center justify-center">
                <svg className="animate-spin h-5 w-5 mr-3" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                分析中...
              </span>
            ) : (
              '球速を測定'
            )}
          </button>

          {error && (
            <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-red-700 font-semibold">⚠️ エラー</p>
              <p className="text-red-600 text-sm mt-1">{error}</p>

              {errorDetails && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-red-500 hover:text-red-700 select-none">
                    🔍 エラー詳細を表示
                  </summary>
                  <div className="mt-2 p-3 bg-red-100 rounded text-xs font-mono">
                    <pre className="whitespace-pre-wrap break-all">
                      {JSON.stringify(errorDetails, null, 2)}
                    </pre>
                  </div>
                </details>
              )}
            </div>
          )}

          {result && (
            <div className="mt-6 p-6 bg-gradient-to-r from-green-50 to-emerald-50 border-2 border-green-200 rounded-lg">
              <div className="text-center mb-4">
                <p className="text-green-700 font-semibold text-lg mb-2">✅ 測定完了!</p>
              </div>
              
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="bg-white p-4 rounded-lg shadow">
                  <p className="text-gray-600 text-sm">球速</p>
                  <p className="text-3xl font-bold text-blue-600">
                    {result.speed_kmh}
                  </p>
                  <p className="text-gray-500 text-sm">km/h</p>
                </div>
                
                <div className="bg-white p-4 rounded-lg shadow">
                  <p className="text-gray-600 text-sm">球速</p>
                  <p className="text-3xl font-bold text-green-600">
                    {result.speed_mph}
                  </p>
                  <p className="text-gray-500 text-sm">mph</p>
                </div>
              </div>

              <div className="bg-white p-4 rounded-lg space-y-2 text-sm mb-4">
                <div className="flex justify-between">
                  <span className="text-gray-600">検出フレーム数:</span>
                  <span className="font-semibold">{result.detected_frames}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">動画FPS:</span>
                  <span className="font-semibold">{result.fps?.toFixed(1)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">追跡時間:</span>
                  <span className="font-semibold">{result.tracking_duration_ms} ms</span>
                </div>
                <div className="flex justify-between border-t pt-2">
                  <span className="text-gray-600">キャリブレーション:</span>
                  <span className="font-semibold flex items-center">
                    {result.calibration_method}
                    {result.mitt_detected ? (
                      <span className="ml-2 text-green-600">✓</span>
                    ) : (
                      <span className="ml-2 text-yellow-600">⚠</span>
                    )}
                  </span>
                </div>
                {result.slowmo_factor && result.slowmo_factor > 1 && (
                  <div className="flex justify-between text-xs text-blue-600 font-semibold">
                    <span>スローモーション補正:</span>
                    <span>{result.slowmo_factor}x</span>
                  </div>
                )}
                {result.scale_factor && (
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>スケール係数:</span>
                    <span>{result.scale_factor} m/pixel</span>
                  </div>
                )}
              </div>

              {result.warning && (
                <div className="mb-4 p-3 bg-yellow-50 border border-yellow-300 rounded">
                  <p className="text-yellow-800 text-sm font-semibold">⚠️ 警告</p>
                  <p className="text-yellow-700 text-xs mt-1">
                    {result.warning}
                  </p>
                </div>
              )}

              {!result.mitt_detected && (
                <div className="mb-4 p-3 bg-orange-50 border border-orange-200 rounded">
                  <p className="text-orange-800 text-sm font-semibold">📌 ヒント</p>
                  <p className="text-orange-700 text-xs mt-1">
                    キャッチャーミットが検出できませんでした。捕球シーンを含めると精度が向上します。
                  </p>
                </div>
              )}

              {/* デバッグ情報 */}
              <details className="mt-4">
                <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-700 select-none">
                  🔍 詳細なデバッグ情報を表示
                </summary>
                <div className="mt-2 p-3 bg-gray-100 rounded text-xs font-mono">
                  <pre className="whitespace-pre-wrap break-all">
                    {JSON.stringify(result, null, 2)}
                  </pre>
                </div>
              </details>
            </div>
          )}

          <div className="mt-8 p-4 bg-blue-50 rounded-lg">
            <p className="text-sm font-semibold text-blue-900 mb-2">📌 撮影のコツ</p>
            <ul className="text-xs text-blue-800 space-y-1">
              <li>• 240fpsのスローモーション撮影を使用</li>
              <li>• <strong>投球→捕球まで撮影</strong>（逆再生で自動処理）</li>
              <li>• 捕球シーンを含めるとミット検出で精度向上</li>
              <li>• 背景はシンプルに（空や壁など単色が理想）</li>
              <li>• 明るい場所で撮影</li>
              <li>• カメラは固定して横方向から撮影</li>
              <li>• ボールの軌道全体が画面に収まるように</li>
            </ul>
          </div>

          <div className="mt-4 p-4 bg-purple-50 rounded-lg">
            <p className="text-sm font-semibold text-purple-900 mb-2">🎯 仕組み</p>
            <ol className="text-xs text-purple-800 space-y-1">
              <li>1. 動画を逆再生して捕球→投球の順で処理</li>
              <li>2. AIがキャッチャーミット(標準32cm)を検出</li>
              <li>3. ミットサイズから距離を自動計算</li>
              <li>4. ボールの移動距離と時間から球速を算出</li>
              <li>5. キャリブレーション不要で測定完了！</li>
            </ol>
          </div>
        </div>

        <div className="text-center mt-6 text-sm text-gray-600">
          <p>Powered by YOLOv11-nano + BoT-SORT + Auto Mitt Detection</p>
        </div>
      </div>
    </div>
  );
}