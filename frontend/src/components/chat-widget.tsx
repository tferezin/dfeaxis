"use client"

/**
 * ChatWidget — bot de atendimento flutuante.
 *
 * Dois modos:
 *  - "landing" (anônimo) → POST /api/v1/chat/landing
 *  - "dashboard" (autenticado) → POST /api/v1/chat/dashboard
 *
 * Usado pelo dashboard via import direto. Para a landing estática,
 * existe uma versão vanilla-JS em /public/chat-widget.js que consome
 * o mesmo endpoint.
 */

import { useEffect, useRef, useState } from "react"
import { Send, X, MessageCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiFetch } from "@/lib/api"

interface Message {
  role: "user" | "assistant"
  content: string
}

interface ChatWidgetProps {
  context: "landing" | "dashboard"
  currentPage?: string
  // Para landing: apiUrl é o backend completo (porque não usa apiFetch que tem auth)
  apiUrl?: string
}

const GREETING_LANDING: Message = {
  role: "assistant",
  content:
    "Oi! Sou o assistente do DFeAxis. Posso tirar dúvidas sobre captura automática de NF-e, integração com seu ERP, planos ou o trial. Por onde quer começar?",
}

const GREETING_DASHBOARD: Message = {
  role: "assistant",
  content:
    "Olá! Sou o assistente do DFeAxis. Posso te ajudar com: configurar certificados, entender códigos SEFAZ, explicar a API, mostrar seu uso do mês ou resolver dúvidas técnicas. Como posso ajudar?",
}

function getSessionId(): string {
  if (typeof window === "undefined") return ""
  let id = window.localStorage.getItem("dfeaxis:chat_session")
  if (!id) {
    id = crypto.randomUUID()
    window.localStorage.setItem("dfeaxis:chat_session", id)
  }
  return id
}

export function ChatWidget({ context, currentPage, apiUrl }: ChatWidgetProps) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>(
    context === "landing" ? [GREETING_LANDING] : [GREETING_DASHBOARD]
  )
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll para o fim
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, loading])

  async function sendMessage() {
    const text = input.trim()
    if (!text || loading) return

    const userMsg: Message = { role: "user", content: text }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput("")
    setLoading(true)
    setError(null)

    try {
      const payload: Record<string, unknown> = {
        messages: newMessages,
        conversation_id: conversationId,
      }

      if (context === "landing") {
        payload.session_id = getSessionId()
        payload.page_url = typeof window !== "undefined" ? window.location.pathname : undefined
      } else {
        payload.current_page = currentPage
      }

      const endpoint = context === "landing" ? "/chat/landing" : "/chat/dashboard"

      let response: { conversation_id: string; message: string }

      if (context === "landing" && apiUrl) {
        // Landing embedded em HTML estático — usa fetch direto sem auth
        const res = await fetch(`${apiUrl}${endpoint}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        response = await res.json()
      } else {
        // Dashboard — usa apiFetch que injeta JWT
        response = await apiFetch(endpoint, {
          method: "POST",
          body: JSON.stringify(payload),
        })
      }

      setConversationId(response.conversation_id)
      setMessages([...newMessages, { role: "assistant", content: response.message }])
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : "Erro ao enviar mensagem"
      setError(errMsg)
      setMessages([
        ...newMessages,
        {
          role: "assistant",
          content:
            "Desculpa, tive um problema pra processar sua mensagem. Pode tentar novamente em alguns instantes?",
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Abrir chat"
        className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full bg-emerald-600 px-5 py-3 text-white shadow-lg transition-all hover:bg-emerald-700 hover:shadow-xl"
      >
        <MessageCircle className="size-5" />
        <span className="text-sm font-semibold">Dúvidas?</span>
      </button>
    )
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[560px] w-[380px] max-w-[calc(100vw-3rem)] flex-col rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between rounded-t-2xl border-b border-slate-200 bg-emerald-600 px-4 py-3 dark:border-slate-700">
        <div className="flex items-center gap-2 text-white">
          <MessageCircle className="size-5" />
          <div>
            <div className="text-sm font-semibold">Assistente DFeAxis</div>
            <div className="text-[11px] opacity-80">
              {context === "landing" ? "Dúvidas sobre o produto" : "Suporte técnico"}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Fechar chat"
          className="rounded-md p-1 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
        >
          <X className="size-5" />
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4 text-sm">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl bg-slate-100 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              <Loader2 className="size-3 animate-spin" />
              Digitando...
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="border-t border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Input */}
      <div className="border-t border-slate-200 p-3 dark:border-slate-700">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Escreva sua mensagem..."
            rows={2}
            disabled={loading}
            className="flex-1 resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
          />
          <Button
            type="button"
            size="icon"
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="size-10 shrink-0 bg-emerald-600 hover:bg-emerald-700"
          >
            <Send className="size-4" />
          </Button>
        </div>
        <p className="mt-2 text-[10px] text-slate-400 dark:text-slate-500">
          Este chat é gravado para melhorar nosso atendimento. Powered by Claude.
        </p>
      </div>
    </div>
  )
}
