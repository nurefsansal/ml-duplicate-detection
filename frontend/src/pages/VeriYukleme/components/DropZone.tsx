import { useState, useRef } from "react";

interface DropZoneProps {
  onFileSelect: (file: File) => void;
}

export default function DropZone({ onFileSelect }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) onFileSelect(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onFileSelect(file);
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => fileRef.current?.click()}
      className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all duration-200 ${
        isDragging
          ? "border-red-500 bg-red-50"
          : "border-gray-200 hover:border-red-300 hover:bg-red-50/30 bg-gray-50/50"
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
        className={`w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4 transition-colors ${isDragging ? "bg-red-100" : "bg-white border border-gray-100"}`}
      >
        <i
          className={`ri-upload-cloud-2-line text-3xl ${isDragging ? "text-red-600" : "text-gray-400"}`}
        ></i>
      </div>
      {isDragging ? (
        <p className="text-base font-semibold text-red-600">Dosyayı bırakın</p>
      ) : (
        <>
          <p className="text-base font-semibold text-gray-700 mb-1">
            Dosyayı sürükleyip bırakın
          </p>
          <p className="text-sm text-gray-400">
            veya{" "}
            <span className="text-red-600 font-medium">
              dosya seçmek için tıklayın
            </span>
          </p>
          <p className="text-xs text-gray-400 mt-3">
            Desteklenen formatlar: .xlsx, .xls, .csv (maks. 50 MB)
          </p>
        </>
      )}
    </div>
  );
}
