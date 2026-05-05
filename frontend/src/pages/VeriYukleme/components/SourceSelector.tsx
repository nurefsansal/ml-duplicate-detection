interface SourceSelectorProps {
  selected: string;
  onChange: (source: "excel" | "csv" | "api" | "manuel" | "institution") => void;
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
    desc: "Virgüllü ayrılmış",
    color: "blue",
  },
  {
    id: "api",
    icon: "ri-code-s-slash-line",
    label: "API",
    desc: "REST endpoint",
    color: "purple",
  },
  {
    id: "institution",
    icon: "ri-database-2-line",
    label: "Kurum DB",
    desc: "Ayarlar > Kurum DB",
    color: "teal",
  },
  {
    id: "manuel",
    icon: "ri-keyboard-line",
    label: "Manuel",
    desc: "Form ile giriş",
    color: "orange",
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
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {sources.map((src) => {
        const isSelected = selected === src.id;
        const c = colorClasses[src.color as keyof typeof colorClasses];
        return (
          <button
            key={src.id}
            onClick={() => onChange(src.id)}
            className={`p-4 rounded-xl border-2 text-left transition-all duration-150 cursor-pointer ${
              isSelected
                ? `${c.border} border-opacity-100`
                : "border-gray-100 bg-white hover:border-gray-200"
            }`}
          >
            <div
              className={`w-9 h-9 rounded-lg flex items-center justify-center mb-3 ${isSelected ? c.icon : "bg-gray-100 text-gray-500"}`}
            >
              <i className={`${src.icon} text-lg`}></i>
            </div>
            <p
              className={`text-sm font-semibold ${isSelected ? c.text : "text-gray-700"}`}
            >
              {src.label}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">{src.desc}</p>
            {isSelected && (
              <div className="flex items-center gap-1 mt-2">
                <div
                  className={`w-1.5 h-1.5 rounded-full ${isSelected ? c.icon.split(" ")[1] : ""} bg-current`}
                ></div>
                <span className={`text-[10px] font-medium ${c.text}`}>
                  Seçildi
                </span>
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
