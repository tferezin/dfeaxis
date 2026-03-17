import { NextRequest, NextResponse } from "next/server"
import { exec } from "child_process"
import { promisify } from "util"
import path from "path"

const execAsync = promisify(exec)

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const pfxFile = formData.get("pfx") as File | null
    const password = formData.get("password") as string
    const cnpj = formData.get("cnpj") as string
    const tipos = formData.get("tipos") as string || "nfe,cte,mdfe"

    if (!pfxFile || !password || !cnpj) {
      return NextResponse.json(
        { error: "Arquivo .pfx, senha e CNPJ são obrigatórios" },
        { status: 400 }
      )
    }

    // Read PFX and convert to base64
    const pfxBuffer = Buffer.from(await pfxFile.arrayBuffer())
    const pfxBase64 = pfxBuffer.toString("base64")

    const cleanCnpj = cnpj.replace(/\D/g, "")
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "https://dfeaxis-production.up.railway.app"

    // Try calling the backend API on Railway first
    try {
      const response = await fetch(`${backendUrl}/api/v1/test-capture`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pfx_base64: pfxBase64,
          password,
          cnpj: cleanCnpj,
          tipos: tipos.split(","),
        }),
      })

      if (response.ok) {
        const data = await response.json()
        return NextResponse.json(data)
      }
    } catch {
      // Backend API endpoint not available, try local Python script
    }

    // Fallback: execute Python script locally
    try {
      const scriptPath = path.resolve(process.cwd(), "..", "backend", "scripts", "test_sefaz.py")

      const { stdout, stderr } = await execAsync(
        `python3 "${scriptPath}" "${pfxBase64}" "${password}" "${cleanCnpj}" "${tipos}"`,
        { timeout: 120000, maxBuffer: 10 * 1024 * 1024 }
      )

      if (stderr && !stdout) {
        return NextResponse.json(
          { error: "Erro ao executar consulta SEFAZ", details: stderr },
          { status: 500 }
        )
      }

      const result = JSON.parse(stdout.trim())
      return NextResponse.json(result)
    } catch {
      return NextResponse.json({
        error: "Backend não disponível. Verifique se o serviço está rodando.",
        backend_url: backendUrl,
      }, { status: 503 })
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)

    if (message.includes("python3") || message.includes("No such file")) {
      return NextResponse.json({
        error: "Python3 não encontrado ou dependências não instaladas.",
        message: "Execute: cd backend && pip install -r requirements.txt",
      }, { status: 500 })
    }

    return NextResponse.json(
      { error: "Erro ao processar requisição", details: message },
      { status: 500 }
    )
  }
}
