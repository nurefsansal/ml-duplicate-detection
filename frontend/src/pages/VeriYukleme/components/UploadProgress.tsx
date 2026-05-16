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
    <div className="ui-card p-6 shadow-card-lg">
      <div className="mb-4 flex items-center gap-3">
        <div
          className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${
            isDone ? "bg-emerald-50" : "bg-primary-50"
          }`}
        >
          <i
            className={`text-lg ${isDone ? "ri-checkbox-circle-fill text-emerald-600" : "ri-loader-4-line animate-spin text-primary-700"}`}
          />
        </div>

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-slate-900">{fileName}</p>
          <p className="text-xs font-medium text-slate-500">
            {isDone ? "Yükleme tamamlandı" : `Dosya yükleniyor... %${progress}`}
          </p>
        </div>

        {!isDone && (
          <button
            type="button"
            onClick={onCancel}
            className="cursor-pointer whitespace-nowrap text-xs font-medium text-slate-400 transition-colors hover:text-danger-600"
          >
            İptal
          </button>
        )}
      </div>

      <div className="h-2 overflow-hidden rounded-full bg-slate-100 shadow-inner">
        <div
          className={`h-2 rounded-full transition-all duration-300 ${
            isDone ? "bg-emerald-500" : "bg-gradient-to-r from-primary-500 to-indigo-500"
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {isDone && (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-emerald-100 bg-emerald-50 p-3">
          <i className="ri-checkbox-circle-line text-sm text-emerald-600" />
          <p className="text-xs font-medium text-emerald-900">
            Dosya başarıyla yüklendi. Şimdi standardizasyon adımına geçebilirsiniz.
          </p>
        </div>
      )}
    </div>
  );
}
