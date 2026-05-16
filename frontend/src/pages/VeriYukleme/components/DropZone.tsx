import { useRef, useState } from "react";

interface DropZoneProps {
  onFileSelect: (file: File) => void;
}

export default function DropZone({ onFileSelect }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) onFileSelect(file);
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) onFileSelect(file);
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => fileRef.current?.click()}
      className={`cursor-pointer rounded-xl border-2 border-dashed px-6 py-8 text-center transition-all duration-200 ${
        isDragging
          ? "border-primary-500 bg-primary-50 shadow-inner ring-2 ring-primary-200/60"
          : "border-slate-200 bg-slate-50/60 hover:border-primary-300 hover:bg-primary-50/40"
      }`}
    >
      <input
        ref={fileRef}
        type="file"
        accept=".xlsx,.xls,.csv"
        className="hidden"
        onChange={handleFileChange}
      />

      <div
        className={`mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl transition-colors ${
          isDragging ? "bg-primary-100" : "border border-slate-100 bg-white shadow-sm"
        }`}
      >
        <i
          className={`ri-upload-cloud-2-line text-2xl ${
            isDragging ? "text-primary-700" : "text-slate-400"
          }`}
        />
      </div>

      {isDragging ? (
        <p className="text-sm font-semibold text-primary-800">Dosyayı buraya bırakın</p>
      ) : (
        <>
          <p className="mb-0.5 text-sm font-semibold text-slate-800">
            Excel veya CSV dosyanızı sürükleyin
          </p>
          <p className="text-xs text-slate-500">
            veya{" "}
            <span className="font-semibold text-primary-700">bilgisayarınızdan seçmek için tıklayın</span>
          </p>
          <p className="mt-2 text-[11px] text-slate-400">
            Desteklenen dosyalar: .xlsx, .xls, .csv (en fazla 100 MB)
          </p>
        </>
      )}
    </div>
  );
}
