interface SourceSelectorProps {
  selected: string;
  onChange: (source: "excel" | "csv" | "api" | "institution") => void;
}

const sources = [
  {
    id: "excel",
    icon: "ri-file-excel-2-line",
    label: "Excel",
    desc: ".xlsx, .xls",
    color: "green",
  },
  {
    id: "csv",
    icon: "ri-file-text-line",
    label: "CSV",
    desc: "Virgülle ayrılmış dosya",
    color: "blue",
  },
  {
    id: "api",
    icon: "ri-code-s-slash-line",
    label: "API",
    desc: "Servis bağlantısı",
    color: "purple",
  },
  {
    id: "institution",
    icon: "ri-database-2-line",
    label: "Kurum Veritabanı",
    desc: "PostgreSQL tablodan içe aktar",
    color: "teal",
  },
] as const;

const colorClasses = {
  green: {
    border: "border-green-200 bg-green-50",
    icon: "text-green-600 bg-green-100",
    text: "text-green-700",
  },
  blue: {
    border: "border-blue-200 bg-blue-50",
    icon: "text-blue-600 bg-blue-100",
    text: "text-blue-700",
  },
  purple: {
    border: "border-purple-200 bg-purple-50",
    icon: "text-purple-600 bg-purple-100",
    text: "text-purple-700",
  },
  orange: {
    border: "border-orange-200 bg-orange-50",
    icon: "text-orange-600 bg-orange-100",
    text: "text-orange-700",
  },
  teal: {
    border: "border-teal-200 bg-teal-50",
    icon: "text-teal-600 bg-teal-100",
    text: "text-teal-700",
  },
};

export default function SourceSelector({
  selected,
  onChange,
}: SourceSelectorProps) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {sources.map((src) => {
        const isSelected = selected === src.id;
        const c = colorClasses[src.color as keyof typeof colorClasses];
        return (
          <button
            key={src.id}
            onClick={() => onChange(src.id)}
            className={`cursor-pointer rounded-xl border-2 p-4 text-left transition-all duration-150 ${
              isSelected
                ? `${c.border} border-opacity-100`
                : "border-gray-100 bg-white hover:border-gray-200"
            }`}
          >
            <div
              className={`mb-3 flex h-9 w-9 items-center justify-center rounded-lg ${isSelected ? c.icon : "bg-gray-100 text-gray-500"}`}
            >
              <i className={`${src.icon} text-lg`} />
            </div>
            <p
              className={`text-sm font-semibold ${isSelected ? c.text : "text-gray-700"}`}
            >
              {src.label}
            </p>
            <p className="mt-0.5 text-xs text-gray-400">{src.desc}</p>
            {isSelected && (
              <div className="mt-2 flex items-center gap-1">
                <div
                  className={`h-1.5 w-1.5 rounded-full ${isSelected ? c.icon.split(" ")[1] : ""} bg-current`}
                />
                <span className={`text-[10px] font-medium ${c.text}`}>
                  Seçili
                </span>
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
