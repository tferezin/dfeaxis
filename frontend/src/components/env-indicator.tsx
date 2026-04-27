"use client"

/**
 * Filtro de VISUALIZAÇÃO do dashboard — permite ao usuário ver os dados
 * agrupados por Homologação ou Produção. NÃO altera o ambiente ativo de
 * captura (a troca real é feita exclusivamente em Cadastros → Configurações,
 * com re-autenticação por senha).
 */
export function EnvIndicator({
  value,
  onChange,
}: {
  value: "1" | "2"
  onChange: (next: "1" | "2") => void
}) {
  const baseSeg =
    "inline-flex items-center justify-center px-3 py-1 text-xs font-medium rounded-full transition-colors"
  const active = "bg-emerald-500 text-white shadow-sm"
  const inactive = "text-muted-foreground hover:text-foreground"

  return (
    <div
      role="group"
      aria-label="Filtro de visualização do ambiente"
      className="inline-flex items-center gap-1 rounded-full border bg-background p-0.5 shadow-sm"
    >
      <button
        type="button"
        onClick={() => onChange("2")}
        aria-pressed={value === "2"}
        className={`${baseSeg} ${value === "2" ? active : inactive}`}
      >
        Homologação
      </button>
      <button
        type="button"
        onClick={() => onChange("1")}
        aria-pressed={value === "1"}
        className={`${baseSeg} ${value === "1" ? active : inactive}`}
      >
        Produção
      </button>
    </div>
  )
}
