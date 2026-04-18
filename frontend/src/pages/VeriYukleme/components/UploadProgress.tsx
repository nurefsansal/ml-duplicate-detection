interface UploadProgressProps {
  progress: number;
  fileName: string;
  onCancel: () => void;
}

export default function UploadProgress({
  progress,
  fileName,
  onCancel,
}: UploadProgressProps) {
  const isDone = progress >= 100;

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-5">
      <div className="flex items-center gap-3 mb-4">
        <div
          className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${isDone ? "bg-green-50" : "bg-red-50"}`}
        >
          <i
            className={`text-lg ${isDone ? "ri-checkbox-circle-fill text-green-600" : "ri-loader-4-line text-red-600 animate-spin"}`}
          ></i>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-800 truncate">
            {fileName}
          </p>
          <p className="text-xs text-gray-400">
            {isDone ? "Yükleme tamamlandı" : `Yükleniyor... %${progress}`}
          </p>
        </div>
        {!isDone && (
          <button
            onClick={onCancel}
            className="text-xs text-gray-400 hover:text-red-500 cursor-pointer transition-colors whitespace-nowrap"
          >
            İptal
          </button>
        )}
      </div>
      <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all duration-300 ${isDone ? "bg-green-500" : "bg-red-500"}`}
          style={{ width: `${progress}%` }}
        ></div>
      </div>
      {isDone && (
        <div className="mt-4 p-3 bg-green-50 rounded-lg flex items-center gap-2">
          <i className="ri-checkbox-circle-line text-green-600 text-sm"></i>
          <p className="text-xs text-green-700 font-medium">
            Dosya başarıyla yüklendi. Normalizasyon için hazır.
          </p>
        </div>
      )}
    </div>
  );
}
