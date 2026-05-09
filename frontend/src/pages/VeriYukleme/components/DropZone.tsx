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

      className={`cursor-pointer rounded-2xl border-2 border-dashed p-12 text-center transition-all duration-200 ${

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

        className={`mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl transition-colors ${

          isDragging ? "bg-primary-100" : "border border-slate-100 bg-white shadow-sm"

        }`}

      >

        <i

          className={`ri-upload-cloud-2-line text-3xl ${isDragging ? "text-primary-700" : "text-slate-400"}`}

        />

      </div>

      {isDragging ? (

        <p className="text-base font-semibold text-primary-800">Dosyayı bırakın</p>

      ) : (

        <>

          <p className="mb-1 text-base font-semibold text-slate-800">

            Dosyayı sürükleyip bırakın

          </p>

          <p className="text-sm text-slate-500">

            veya{" "}

            <span className="font-semibold text-primary-700">

              dosya seçmek için tıklayın

            </span>

          </p>

          <p className="mt-3 text-xs text-slate-400">

            Desteklenen formatlar: .xlsx, .xls, .csv (maks. 100 MB)

          </p>

        </>

      )}

    </div>

  );

}

