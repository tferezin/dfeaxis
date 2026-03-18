"use client"

import { useState, useEffect, useCallback } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useSettings } from "@/hooks/use-settings"
import { getSupabase } from "@/lib/supabase"
import { cn } from "@/lib/utils"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Filter,
  FileDown,
  ChevronLeft,
  ChevronRight,
  Loader2,
  CheckCircle2,
  Download,
  Inbox,
} from "lucide-react"

type NfeStatus = "Pendente" | "Ciencia" | "Disponivel" | "Entregue" | "Cancelada"

interface NfeRow {
  id: number
  emitente: string
  cnpj: string
  emissao: string
  nota: string
  chave: string
  valor: number
  status: NfeStatus
  entregueEm?: string
}

const statusConfig: Record<NfeStatus, { label: string; description: string; className: string }> = {
  Pendente: {
    label: "Pendente",
    description: "Resumo detectado, aguardando ciência",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  },
  Ciencia: {
    label: "Ciencia",
    description: "Ciência enviada, aguardando XML completo",
    className: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  },
  Disponivel: {
    label: "Disponivel",
    description: "XML completo pronto para download pelo SAP",
    className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  },
  Entregue: {
    label: "Entregue",
    description: "SAP já baixou e confirmou",
    className: "bg-gray-100 text-gray-600 dark:bg-gray-800/50 dark:text-gray-400",
  },
  Cancelada: {
    label: "Cancelada",
    description: "Nota cancelada na SEFAZ",
    className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  },
}

const mockData: NfeRow[] = [
  // Pendentes (5)
  { id: 1, emitente: "Distribuidora Alimentos Ltda", cnpj: "12.345.678/0001-90", emissao: "17/03/2026", nota: "001.234.567", chave: "3526 0312 3456 7800 0190 5500 1001 2345 6712 3456 7890", valor: 15420.50, status: "Pendente" },
  { id: 2, emitente: "Auto Pecas Centro Sul", cnpj: "66.777.888/0001-99", emissao: "17/03/2026", nota: "006.789.012", chave: "3526 0366 7778 8800 0199 5500 1006 7890 1267 8901 2345", valor: 4560.30, status: "Pendente" },
  { id: 3, emitente: "Grafica Express ME", cnpj: "77.888.999/0001-00", emissao: "16/03/2026", nota: "007.890.123", chave: "3526 0377 8889 9900 0100 5500 1007 8901 2378 9012 3456", valor: 1280.00, status: "Pendente" },
  { id: 4, emitente: "Transportadora Veloz S.A.", cnpj: "10.111.222/0001-33", emissao: "16/03/2026", nota: "010.123.456", chave: "3526 0310 1112 2200 0133 5500 1010 1234 5601 2345 6789", valor: 12300.00, status: "Pendente" },
  { id: 5, emitente: "Posto Combustivel Rota", cnpj: "76.888.999/0001-00", emissao: "16/03/2026", nota: "016.789.012", chave: "3526 0376 8889 9900 0100 5500 1016 7890 1267 8901 2345", valor: 3210.40, status: "Pendente" },
  // Ciencia (2)
  { id: 6, emitente: "Metalurgica Brasil ME", cnpj: "11.222.333/0001-44", emissao: "15/03/2026", nota: "003.456.789", chave: "3526 0311 2223 3300 0144 5500 1003 4567 8934 5678 9012", valor: 32100.75, status: "Ciencia" },
  { id: 7, emitente: "Supermercado Bom Preco", cnpj: "99.000.111/0001-22", emissao: "15/03/2026", nota: "009.012.345", chave: "3526 0399 0001 1100 0122 5500 1009 0123 4590 1234 5678", valor: 540.80, status: "Ciencia" },
  // Disponiveis (8)
  { id: 8, emitente: "Tech Solutions S.A.", cnpj: "98.765.432/0001-10", emissao: "15/03/2026", nota: "002.345.678", chave: "3526 0398 7654 3200 0110 5500 1002 3456 7823 4567 8901", valor: 8750.00, status: "Disponivel" },
  { id: 9, emitente: "Eletro Comercial Eireli", cnpj: "32.444.555/0001-66", emissao: "14/03/2026", nota: "012.345.678", chave: "3526 0332 4445 5500 0166 5500 1012 3456 7823 4567 8901", valor: 23450.00, status: "Disponivel" },
  { id: 10, emitente: "Textil Nordeste ME", cnpj: "65.777.888/0001-99", emissao: "14/03/2026", nota: "015.678.901", chave: "3526 0365 7778 8800 0199 5500 1015 6789 0156 7890 1234", valor: 45230.80, status: "Disponivel" },
  { id: 11, emitente: "Clinica Odonto Plus", cnpj: "98.000.111/0001-22", emissao: "13/03/2026", nota: "018.901.234", chave: "3526 0398 0001 1100 0122 5500 1018 9012 3489 0123 4567", valor: 4890.00, status: "Disponivel" },
  { id: 12, emitente: "Industria Quimica Norte", cnpj: "88.999.000/0001-11", emissao: "13/03/2026", nota: "008.901.234", chave: "3526 0388 9990 0000 0111 5500 1008 9012 3489 0123 4567", valor: 67890.45, status: "Disponivel" },
  { id: 13, emitente: "Laboratorio Vida Saude", cnpj: "54.666.777/0001-88", emissao: "12/03/2026", nota: "014.567.890", chave: "3526 0354 6667 7700 0188 5500 1014 5678 9045 6789 0123", valor: 7650.00, status: "Disponivel" },
  { id: 14, emitente: "Agropecuaria Campo Verde", cnpj: "87.999.000/0001-11", emissao: "12/03/2026", nota: "017.890.123", chave: "3526 0387 9990 0000 0111 5500 1017 8901 2378 9012 3456", valor: 156780.00, status: "Disponivel" },
  { id: 15, emitente: "Papelaria Central Ltda", cnpj: "23.456.789/0001-01", emissao: "11/03/2026", nota: "019.012.345", chave: "3526 0323 4567 8900 0101 5500 1019 0123 4501 2345 6789", valor: 2340.00, status: "Disponivel" },
  // Entregues (42 - showing representative subset for mock)
  { id: 16, emitente: "Construtora Horizonte Ltda", cnpj: "55.666.777/0001-88", emissao: "11/03/2026", nota: "005.678.901", chave: "3526 0355 6667 7700 0188 5500 1005 6789 0156 7890 1234", valor: 98500.00, status: "Entregue", entregueEm: "11/03/2026 14:32" },
  { id: 17, emitente: "Padaria Sao Jorge Ltda", cnpj: "21.333.444/0001-55", emissao: "10/03/2026", nota: "011.234.567", chave: "3526 0321 3334 4400 0155 5500 1011 2345 6712 3456 7890", valor: 890.25, status: "Entregue", entregueEm: "10/03/2026 09:15" },
  { id: 18, emitente: "Farmacia Popular Eireli", cnpj: "44.555.666/0001-77", emissao: "10/03/2026", nota: "020.345.678", chave: "3526 0344 5556 6600 0177 5500 1020 3456 7823 4567 8901", valor: 5670.00, status: "Entregue", entregueEm: "10/03/2026 16:48" },
  { id: 19, emitente: "Distribuidora Alimentos Ltda", cnpj: "12.345.678/0001-90", emissao: "09/03/2026", nota: "021.456.789", chave: "3526 0312 3456 7800 0190 5500 1021 4567 8934 5678 9012", valor: 22340.00, status: "Entregue", entregueEm: "09/03/2026 11:22" },
  { id: 20, emitente: "Tech Solutions S.A.", cnpj: "98.765.432/0001-10", emissao: "09/03/2026", nota: "022.567.890", chave: "3526 0398 7654 3200 0110 5500 1022 5678 9045 6789 0123", valor: 14200.00, status: "Entregue", entregueEm: "09/03/2026 08:05" },
  { id: 21, emitente: "Metalurgica Brasil ME", cnpj: "11.222.333/0001-44", emissao: "08/03/2026", nota: "023.678.901", chave: "3526 0311 2223 3300 0144 5500 1023 6789 0156 7890 1234", valor: 41500.00, status: "Entregue", entregueEm: "08/03/2026 15:33" },
  { id: 22, emitente: "Auto Pecas Centro Sul", cnpj: "66.777.888/0001-99", emissao: "08/03/2026", nota: "024.789.012", chave: "3526 0366 7778 8800 0199 5500 1024 7890 1267 8901 2345", valor: 3890.50, status: "Entregue", entregueEm: "08/03/2026 10:17" },
  { id: 23, emitente: "Supermercado Bom Preco", cnpj: "99.000.111/0001-22", emissao: "07/03/2026", nota: "025.890.123", chave: "3526 0399 0001 1100 0122 5500 1025 8901 2378 9012 3456", valor: 1230.00, status: "Entregue", entregueEm: "07/03/2026 13:41" },
  { id: 24, emitente: "Eletro Comercial Eireli", cnpj: "32.444.555/0001-66", emissao: "07/03/2026", nota: "026.901.234", chave: "3526 0332 4445 5500 0166 5500 1026 9012 3489 0123 4567", valor: 18760.00, status: "Entregue", entregueEm: "07/03/2026 09:58" },
  { id: 25, emitente: "Industria Quimica Norte", cnpj: "88.999.000/0001-11", emissao: "06/03/2026", nota: "027.012.345", chave: "3526 0388 9990 0000 0111 5500 1027 0123 4590 1234 5678", valor: 54320.00, status: "Entregue", entregueEm: "06/03/2026 14:12" },
  { id: 26, emitente: "Laboratorio Vida Saude", cnpj: "54.666.777/0001-88", emissao: "06/03/2026", nota: "028.123.456", chave: "3526 0354 6667 7700 0188 5500 1028 1234 5601 2345 6789", valor: 9870.00, status: "Entregue", entregueEm: "06/03/2026 11:30" },
  { id: 27, emitente: "Construtora Horizonte Ltda", cnpj: "55.666.777/0001-88", emissao: "05/03/2026", nota: "029.234.567", chave: "3526 0355 6667 7700 0188 5500 1029 2345 6712 3456 7890", valor: 76500.00, status: "Entregue", entregueEm: "05/03/2026 16:05" },
  { id: 28, emitente: "Transportadora Veloz S.A.", cnpj: "10.111.222/0001-33", emissao: "05/03/2026", nota: "030.345.678", chave: "3526 0310 1112 2200 0133 5500 1030 3456 7823 4567 8901", valor: 8900.00, status: "Entregue", entregueEm: "05/03/2026 08:44" },
  { id: 29, emitente: "Padaria Sao Jorge Ltda", cnpj: "21.333.444/0001-55", emissao: "04/03/2026", nota: "031.456.789", chave: "3526 0321 3334 4400 0155 5500 1031 4567 8934 5678 9012", valor: 1120.00, status: "Entregue", entregueEm: "04/03/2026 10:22" },
  { id: 30, emitente: "Textil Nordeste ME", cnpj: "65.777.888/0001-99", emissao: "04/03/2026", nota: "032.567.890", chave: "3526 0365 7778 8800 0199 5500 1032 5678 9045 6789 0123", valor: 33450.00, status: "Entregue", entregueEm: "04/03/2026 15:18" },
  { id: 31, emitente: "Agropecuaria Campo Verde", cnpj: "87.999.000/0001-11", emissao: "03/03/2026", nota: "033.678.901", chave: "3526 0387 9990 0000 0111 5500 1033 6789 0156 7890 1234", valor: 128900.00, status: "Entregue", entregueEm: "03/03/2026 09:55" },
  { id: 32, emitente: "Clinica Odonto Plus", cnpj: "98.000.111/0001-22", emissao: "03/03/2026", nota: "034.789.012", chave: "3526 0398 0001 1100 0122 5500 1034 7890 1267 8901 2345", valor: 3450.00, status: "Entregue", entregueEm: "03/03/2026 14:07" },
  { id: 33, emitente: "Grafica Express ME", cnpj: "77.888.999/0001-00", emissao: "02/03/2026", nota: "035.890.123", chave: "3526 0377 8889 9900 0100 5500 1035 8901 2378 9012 3456", valor: 2100.00, status: "Entregue", entregueEm: "02/03/2026 11:33" },
  { id: 34, emitente: "Farmacia Popular Eireli", cnpj: "44.555.666/0001-77", emissao: "02/03/2026", nota: "036.901.234", chave: "3526 0344 5556 6600 0177 5500 1036 9012 3489 0123 4567", valor: 7890.00, status: "Entregue", entregueEm: "02/03/2026 08:19" },
  { id: 35, emitente: "Posto Combustivel Rota", cnpj: "76.888.999/0001-00", emissao: "01/03/2026", nota: "037.012.345", chave: "3526 0376 8889 9900 0100 5500 1037 0123 4590 1234 5678", valor: 5670.00, status: "Entregue", entregueEm: "01/03/2026 16:45" },
  { id: 36, emitente: "Distribuidora Alimentos Ltda", cnpj: "12.345.678/0001-90", emissao: "01/03/2026", nota: "038.123.456", chave: "3526 0312 3456 7800 0190 5500 1038 1234 5601 2345 6789", valor: 19800.00, status: "Entregue", entregueEm: "01/03/2026 10:02" },
  { id: 37, emitente: "Tech Solutions S.A.", cnpj: "98.765.432/0001-10", emissao: "28/02/2026", nota: "039.234.567", chave: "3526 0298 7654 3200 0110 5500 1039 2345 6712 3456 7890", valor: 11200.00, status: "Entregue", entregueEm: "28/02/2026 13:28" },
  { id: 38, emitente: "Metalurgica Brasil ME", cnpj: "11.222.333/0001-44", emissao: "28/02/2026", nota: "040.345.678", chave: "3526 0211 2223 3300 0144 5500 1040 3456 7823 4567 8901", valor: 37600.00, status: "Entregue", entregueEm: "28/02/2026 09:41" },
  { id: 39, emitente: "Supermercado Bom Preco", cnpj: "99.000.111/0001-22", emissao: "27/02/2026", nota: "041.456.789", chave: "3526 0299 0001 1100 0122 5500 1041 4567 8934 5678 9012", valor: 980.00, status: "Entregue", entregueEm: "27/02/2026 15:55" },
  { id: 40, emitente: "Eletro Comercial Eireli", cnpj: "32.444.555/0001-66", emissao: "27/02/2026", nota: "042.567.890", chave: "3526 0232 4445 5500 0166 5500 1042 5678 9045 6789 0123", valor: 21340.00, status: "Entregue", entregueEm: "27/02/2026 10:13" },
  { id: 41, emitente: "Construtora Horizonte Ltda", cnpj: "55.666.777/0001-88", emissao: "26/02/2026", nota: "043.678.901", chave: "3526 0255 6667 7700 0188 5500 1043 6789 0156 7890 1234", valor: 89100.00, status: "Entregue", entregueEm: "26/02/2026 14:37" },
  { id: 42, emitente: "Industria Quimica Norte", cnpj: "88.999.000/0001-11", emissao: "26/02/2026", nota: "044.789.012", chave: "3526 0288 9990 0000 0111 5500 1044 7890 1267 8901 2345", valor: 45600.00, status: "Entregue", entregueEm: "26/02/2026 08:50" },
  { id: 43, emitente: "Laboratorio Vida Saude", cnpj: "54.666.777/0001-88", emissao: "25/02/2026", nota: "045.890.123", chave: "3526 0254 6667 7700 0188 5500 1045 8901 2378 9012 3456", valor: 6540.00, status: "Entregue", entregueEm: "25/02/2026 11:09" },
  { id: 44, emitente: "Transportadora Veloz S.A.", cnpj: "10.111.222/0001-33", emissao: "25/02/2026", nota: "046.901.234", chave: "3526 0210 1112 2200 0133 5500 1046 9012 3489 0123 4567", valor: 7230.00, status: "Entregue", entregueEm: "25/02/2026 15:22" },
  { id: 45, emitente: "Agropecuaria Campo Verde", cnpj: "87.999.000/0001-11", emissao: "24/02/2026", nota: "047.012.345", chave: "3526 0287 9990 0000 0111 5500 1047 0123 4590 1234 5678", valor: 112000.00, status: "Entregue", entregueEm: "24/02/2026 09:33" },
  { id: 46, emitente: "Padaria Sao Jorge Ltda", cnpj: "21.333.444/0001-55", emissao: "24/02/2026", nota: "048.123.456", chave: "3526 0221 3334 4400 0155 5500 1048 1234 5601 2345 6789", valor: 760.00, status: "Entregue", entregueEm: "24/02/2026 13:47" },
  { id: 47, emitente: "Auto Pecas Centro Sul", cnpj: "66.777.888/0001-99", emissao: "23/02/2026", nota: "049.234.567", chave: "3526 0266 7778 8800 0199 5500 1049 2345 6712 3456 7890", valor: 5430.00, status: "Entregue", entregueEm: "23/02/2026 10:55" },
  { id: 48, emitente: "Textil Nordeste ME", cnpj: "65.777.888/0001-99", emissao: "23/02/2026", nota: "050.345.678", chave: "3526 0265 7778 8800 0199 5500 1050 3456 7823 4567 8901", valor: 28900.00, status: "Entregue", entregueEm: "23/02/2026 16:10" },
  { id: 49, emitente: "Posto Combustivel Rota", cnpj: "76.888.999/0001-00", emissao: "22/02/2026", nota: "051.456.789", chave: "3526 0276 8889 9900 0100 5500 1051 4567 8934 5678 9012", valor: 4120.00, status: "Entregue", entregueEm: "22/02/2026 08:28" },
  { id: 50, emitente: "Clinica Odonto Plus", cnpj: "98.000.111/0001-22", emissao: "22/02/2026", nota: "052.567.890", chave: "3526 0298 0001 1100 0122 5500 1052 5678 9045 6789 0123", valor: 2890.00, status: "Entregue", entregueEm: "22/02/2026 14:52" },
  { id: 51, emitente: "Farmacia Popular Eireli", cnpj: "44.555.666/0001-77", emissao: "21/02/2026", nota: "053.678.901", chave: "3526 0244 5556 6600 0177 5500 1053 6789 0156 7890 1234", valor: 6780.00, status: "Entregue", entregueEm: "21/02/2026 11:40" },
  { id: 52, emitente: "Grafica Express ME", cnpj: "77.888.999/0001-00", emissao: "21/02/2026", nota: "054.789.012", chave: "3526 0277 8889 9900 0100 5500 1054 7890 1267 8901 2345", valor: 1890.00, status: "Entregue", entregueEm: "21/02/2026 09:15" },
  { id: 53, emitente: "Distribuidora Alimentos Ltda", cnpj: "12.345.678/0001-90", emissao: "20/02/2026", nota: "055.890.123", chave: "3526 0212 3456 7800 0190 5500 1055 8901 2378 9012 3456", valor: 17650.00, status: "Entregue", entregueEm: "20/02/2026 15:08" },
  { id: 54, emitente: "Tech Solutions S.A.", cnpj: "98.765.432/0001-10", emissao: "20/02/2026", nota: "056.901.234", chave: "3526 0298 7654 3200 0110 5500 1056 9012 3489 0123 4567", valor: 9430.00, status: "Entregue", entregueEm: "20/02/2026 10:30" },
  { id: 55, emitente: "Supermercado Bom Preco", cnpj: "99.000.111/0001-22", emissao: "19/02/2026", nota: "057.012.345", chave: "3526 0299 0001 1100 0122 5500 1057 0123 4590 1234 5678", valor: 1450.00, status: "Entregue", entregueEm: "19/02/2026 13:22" },
  // Canceladas (2 to bring variety)
  { id: 56, emitente: "Moveis Planejados Sul", cnpj: "43.555.666/0001-77", emissao: "14/03/2026", nota: "013.456.789", chave: "3526 0343 5556 6600 0177 5500 1013 4567 8934 5678 9012", valor: 18900.60, status: "Cancelada" },
  { id: 57, emitente: "Farmacia Popular Eireli", cnpj: "44.555.666/0001-77", emissao: "13/03/2026", nota: "004.567.890", chave: "3526 0344 5556 6600 0177 5500 1004 5678 9045 6789 0123", valor: 2340.20, status: "Cancelada" },
]

const CNPJS = [
  "Todos",
  "12.345.678/0001-90",
  "98.765.432/0001-10",
  "11.222.333/0001-44",
  "55.666.777/0001-88",
  "66.777.888/0001-99",
]

function StatusBadge({ status }: { status: NfeStatus }) {
  const config = statusConfig[status]
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${config.className}`}
      title={config.description}
    >
      {config.label}
    </span>
  )
}

function ActionCell({ row }: { row: NfeRow }) {
  switch (row.status) {
    case "Pendente":
      return (
        <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
          <CheckCircle2 className="size-3.5" />
          Dar Ciência
        </Button>
      )
    case "Ciencia":
      return (
        <Button variant="ghost" size="sm" className="h-7 gap-1.5 text-xs text-muted-foreground" disabled>
          <Loader2 className="size-3.5 animate-spin" />
          Aguardando XML...
        </Button>
      )
    case "Disponivel":
      return (
        <div className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
          <Download className="size-3.5" />
          <span className="font-medium">XML pronto</span>
        </div>
      )
    case "Entregue":
      return (
        <div className="flex flex-col text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="size-3.5" />
            <span>Baixado pelo SAP</span>
          </div>
          {row.entregueEm && (
            <span className="ml-5 text-[11px] text-muted-foreground/70">{row.entregueEm}</span>
          )}
        </div>
      )
    case "Cancelada":
      return (
        <span className="text-xs text-muted-foreground">--</span>
      )
    default:
      return null
  }
}

type TabKey = "pendentes" | "completo"

export default function HistoricoNfePage() {
  const { settings } = useSettings()
  const [activeTab, setActiveTab] = useState<TabKey>("pendentes")
  const [currentPage, setCurrentPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState("Todos")
  const [searchChave, setSearchChave] = useState("")
  const [dateFrom, setDateFrom] = useState("2026-03-01")
  const [dateTo, setDateTo] = useState("2026-03-17")
  const itemsPerPage = 10

  const [realData, setRealData] = useState<any[]>([])
  const [realLoading, setRealLoading] = useState(false)

  const loadRealData = useCallback(async () => {
    setRealLoading(true)
    try {
      const sb = getSupabase()
      const { data, error } = await sb
        .from('documents')
        .select('*')
        .eq('tipo', 'NFE')
        .order('fetched_at', { ascending: false })
        .limit(100)

      if (!error && data) {
        setRealData(data)
      }
    } catch (e) {
      console.error("[DFeAxis] Error loading documents:", e)
    } finally {
      setRealLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!settings.showMockData) {
      loadRealData()
    }
  }, [settings.showMockData, loadRealData])

  if (!settings.showMockData) {
    const statusMap: Record<string, NfeStatus> = {
      available: "Disponivel",
      delivered: "Entregue",
      expired: "Cancelada",
    }

    const mappedData = realData.map((doc, i) => ({
      id: i,
      chave: doc.chave_acesso || "",
      cnpj: doc.cnpj || "",
      status: statusMap[doc.status] || (doc.is_resumo ? "Pendente" : "Disponivel"),
      nsu: doc.nsu || "",
      fetchedAt: doc.fetched_at ? new Date(doc.fetched_at).toLocaleString("pt-BR") : "",
      manifestacao: doc.manifestacao_status || "",
    }))

    const filteredReal = mappedData.filter((row) => {
      if (statusFilter !== "Todos" && row.status !== statusFilter) return false
      if (searchChave && !row.chave.toLowerCase().includes(searchChave.toLowerCase())) return false
      return true
    })

    const totalPagesReal = Math.ceil(filteredReal.length / itemsPerPage)
    const paginatedReal = filteredReal.slice(
      (currentPage - 1) * itemsPerPage,
      currentPage * itemsPerPage
    )

    return (
      <div className="flex flex-col gap-6 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">NF-e Recebidas</h1>
            <p className="text-sm text-muted-foreground">
              Notas fiscais recebidas de fornecedores via captura automática
            </p>
          </div>
          <Button variant="outline" onClick={loadRealData} disabled={realLoading}>
            {realLoading ? <Loader2 className="size-4 animate-spin" /> : <FileDown className="size-4" />}
            {realLoading ? "Carregando..." : "Atualizar"}
          </Button>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-end gap-3 rounded-lg border p-4">
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Status</span>
            <Select value={statusFilter} onValueChange={(v) => { if (v) { setStatusFilter(v); setCurrentPage(1) } }}>
              <SelectTrigger className="w-[150px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Todos">Todos</SelectItem>
                <SelectItem value="Pendente">Pendente</SelectItem>
                <SelectItem value="Disponivel">Disponivel</SelectItem>
                <SelectItem value="Entregue">Entregue</SelectItem>
                <SelectItem value="Cancelada">Cancelada</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Chave de acesso</span>
            <Input
              placeholder="Buscar por chave..."
              className="w-[220px]"
              value={searchChave}
              onChange={(e) => { setSearchChave(e.target.value); setCurrentPage(1) }}
            />
          </div>
          <Button variant="default" className="gap-1.5" onClick={loadRealData} disabled={realLoading}>
            <Filter className="size-3.5" />
            Filtrar
          </Button>
        </div>

        {realLoading ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Loader2 className="size-8 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Carregando documentos...</p>
          </div>
        ) : realData.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 gap-3">
            <Inbox className="size-10 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground text-center max-w-md">
              Nenhum documento capturado. Configure um certificado e execute uma captura para ver documentos reais.
            </p>
          </div>
        ) : (
          <>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Chave de Acesso</TableHead>
                    <TableHead>CNPJ</TableHead>
                    <TableHead>NSU</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Manifestação</TableHead>
                    <TableHead>Capturado em</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedReal.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="max-w-[220px] truncate font-mono text-xs">
                        {row.chave}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{row.cnpj}</TableCell>
                      <TableCell className="font-mono text-xs">{row.nsu}</TableCell>
                      <TableCell>
                        <StatusBadge status={row.status} />
                      </TableCell>
                      <TableCell className="text-xs">{row.manifestacao || "--"}</TableCell>
                      <TableCell className="text-xs">{row.fetchedAt}</TableCell>
                    </TableRow>
                  ))}
                  {paginatedReal.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                        Nenhuma NF-e encontrada com os filtros aplicados.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Mostrando {filteredReal.length === 0 ? 0 : ((currentPage - 1) * itemsPerPage) + 1} a{" "}
                {Math.min(currentPage * itemsPerPage, filteredReal.length)} de{" "}
                {filteredReal.length} registros
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="icon-sm"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage((p) => p - 1)}
                >
                  <ChevronLeft className="size-4" />
                </Button>
                {Array.from({ length: Math.min(totalPagesReal, 5) }, (_, i) => {
                  let page: number
                  if (totalPagesReal <= 5) {
                    page = i + 1
                  } else if (currentPage <= 3) {
                    page = i + 1
                  } else if (currentPage >= totalPagesReal - 2) {
                    page = totalPagesReal - 4 + i
                  } else {
                    page = currentPage - 2 + i
                  }
                  return (
                    <Button
                      key={page}
                      variant={page === currentPage ? "default" : "outline"}
                      size="sm"
                      onClick={() => setCurrentPage(page)}
                    >
                      {page}
                    </Button>
                  )
                })}
                <Button
                  variant="outline"
                  size="icon-sm"
                  disabled={currentPage === totalPagesReal || totalPagesReal === 0}
                  onClick={() => setCurrentPage((p) => p + 1)}
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    )
  }

  // Tab-based data: "pendentes" shows only Pendente + Ciencia; "completo" shows last 50 of all statuses
  const tabData = activeTab === "pendentes"
    ? mockData.filter((row) => row.status === "Pendente" || row.status === "Ciencia")
    : mockData.slice(0, 50)

  const filteredData = tabData.filter((row) => {
    if (statusFilter !== "Todos" && row.status !== statusFilter) return false
    if (searchChave && !row.chave.toLowerCase().includes(searchChave.toLowerCase())) return false
    return true
  })

  const totalPages = Math.ceil(filteredData.length / itemsPerPage)
  const paginatedData = filteredData.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  )

  // Status counts
  const counts = {
    Pendente: tabData.filter((r) => r.status === "Pendente").length,
    Ciencia: tabData.filter((r) => r.status === "Ciencia").length,
    Disponivel: tabData.filter((r) => r.status === "Disponivel").length,
    Entregue: tabData.filter((r) => r.status === "Entregue").length,
    Cancelada: tabData.filter((r) => r.status === "Cancelada").length,
  }
  const total = tabData.length

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">NF-e Recebidas</h1>
          <p className="text-sm text-muted-foreground">
            Notas fiscais recebidas de fornecedores via captura automática
          </p>
        </div>
        <Button variant="outline">
          <FileDown className="size-4" />
          Exportar
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b">
        <button
          onClick={() => { setActiveTab("pendentes"); setCurrentPage(1); setStatusFilter("Todos") }}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "pendentes"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          Pendentes de ação
        </button>
        <button
          onClick={() => { setActiveTab("completo"); setCurrentPage(1); setStatusFilter("Todos") }}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "completo"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          Histórico completo
        </button>
      </div>

      {/* Summary Bar */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-muted/30 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex size-2.5 rounded-full bg-amber-500" />
          <span className="text-sm">Pendentes: <span className="font-semibold">{counts.Pendente}</span></span>
        </div>
        <span className="text-muted-foreground">|</span>
        <div className="flex items-center gap-2">
          <span className="inline-flex size-2.5 rounded-full bg-blue-500" />
          <span className="text-sm">Ciência: <span className="font-semibold">{counts.Ciencia}</span></span>
        </div>
        <span className="text-muted-foreground">|</span>
        <div className="flex items-center gap-2">
          <span className="inline-flex size-2.5 rounded-full bg-green-500" />
          <span className="text-sm">Disponíveis: <span className="font-semibold">{counts.Disponivel}</span></span>
        </div>
        <span className="text-muted-foreground">|</span>
        <div className="flex items-center gap-2">
          <span className="inline-flex size-2.5 rounded-full bg-gray-400" />
          <span className="text-sm">Entregues: <span className="font-semibold">{counts.Entregue}</span></span>
        </div>
        <span className="text-muted-foreground">|</span>
        <div className="flex items-center gap-2">
          <span className="inline-flex size-2.5 rounded-full bg-red-500" />
          <span className="text-sm">Canceladas: <span className="font-semibold">{counts.Cancelada}</span></span>
        </div>
        <span className="text-muted-foreground">|</span>
        <span className="text-sm font-semibold">Total: {total}</span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border p-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">CNPJ</span>
          <Select defaultValue="Todos">
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Selecione o CNPJ" />
            </SelectTrigger>
            <SelectContent>
              {CNPJS.map((cnpj) => (
                <SelectItem key={cnpj} value={cnpj}>
                  {cnpj}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">De</span>
          <Input type="date" className="w-[150px]" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Até</span>
          <Input type="date" className="w-[150px]" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Status</span>
          <Select value={statusFilter} onValueChange={(v) => { if (v) { setStatusFilter(v); setCurrentPage(1) } }}>
            <SelectTrigger className="w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Todos">Todos</SelectItem>
              <SelectItem value="Pendente">Pendente</SelectItem>
              <SelectItem value="Ciencia">Ciência</SelectItem>
              <SelectItem value="Disponivel">Disponível</SelectItem>
              <SelectItem value="Entregue">Entregue</SelectItem>
              <SelectItem value="Cancelada">Cancelada</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Chave de acesso</span>
          <Input
            placeholder="Buscar por chave..."
            className="w-[220px]"
            value={searchChave}
            onChange={(e) => { setSearchChave(e.target.value); setCurrentPage(1) }}
          />
        </div>

        <Button variant="default" className="gap-1.5">
          <Filter className="size-3.5" />
          Filtrar
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Emitente (Fornecedor)</TableHead>
              <TableHead>CNPJ Emitente</TableHead>
              <TableHead>Emissão</TableHead>
              <TableHead>Nota</TableHead>
              <TableHead>Chave de Acesso</TableHead>
              <TableHead className="text-right">Valor (R$)</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedData.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="max-w-[200px] truncate font-medium">
                  {row.emitente}
                </TableCell>
                <TableCell className="font-mono text-xs">{row.cnpj}</TableCell>
                <TableCell>{row.emissao}</TableCell>
                <TableCell className="font-mono text-xs">{row.nota}</TableCell>
                <TableCell className="max-w-[180px] truncate font-mono text-xs">
                  {row.chave}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {row.valor.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </TableCell>
                <TableCell>
                  <StatusBadge status={row.status} />
                </TableCell>
                <TableCell>
                  <ActionCell row={row} />
                </TableCell>
              </TableRow>
            ))}
            {paginatedData.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  Nenhuma NF-e encontrada com os filtros aplicados.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Mostrando {filteredData.length === 0 ? 0 : ((currentPage - 1) * itemsPerPage) + 1} a{" "}
          {Math.min(currentPage * itemsPerPage, filteredData.length)} de{" "}
          {filteredData.length} registros
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon-sm"
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => p - 1)}
          >
            <ChevronLeft className="size-4" />
          </Button>
          {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
            let page: number
            if (totalPages <= 5) {
              page = i + 1
            } else if (currentPage <= 3) {
              page = i + 1
            } else if (currentPage >= totalPages - 2) {
              page = totalPages - 4 + i
            } else {
              page = currentPage - 2 + i
            }
            return (
              <Button
                key={page}
                variant={page === currentPage ? "default" : "outline"}
                size="sm"
                onClick={() => setCurrentPage(page)}
              >
                {page}
              </Button>
            )
          })}
          <Button
            variant="outline"
            size="icon-sm"
            disabled={currentPage === totalPages || totalPages === 0}
            onClick={() => setCurrentPage((p) => p + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
