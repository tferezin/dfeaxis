import { NextRequest, NextResponse } from "next/server"

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const pfxFile = formData.get("pfx") as File | null
    const password = formData.get("password") as string
    const cnpj = formData.get("cnpj") as string

    if (!pfxFile || !password || !cnpj) {
      return NextResponse.json(
        { error: "Arquivo .pfx, senha e CNPJ são obrigatórios" },
        { status: 400 }
      )
    }

    // Read PFX file
    const pfxBuffer = Buffer.from(await pfxFile.arrayBuffer())
    const pfxBase64 = pfxBuffer.toString("base64")

    // Call our backend API (or directly test SEFAZ if backend isn't running)
    // For now, return the connection test info
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

    try {
      // Try calling the backend
      const response = await fetch(`${backendUrl}/api/v1/polling/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pfx_base64: pfxBase64,
          password,
          cnpj: cnpj.replace(/\D/g, ""),
          tipos: ["nfe", "cte"],
        }),
      })

      if (response.ok) {
        const data = await response.json()
        return NextResponse.json(data)
      }
    } catch {
      // Backend not running — return simulated response
    }

    // If backend is not available, return a helpful message
    return NextResponse.json({
      status: "backend_offline",
      message: "O backend FastAPI não está rodando. Para testar a captura real, inicie o backend com: cd backend && uvicorn main:app --reload",
      cnpj: cnpj.replace(/\D/g, ""),
      pfx_size: pfxBuffer.length,
      pfx_valid: pfxBuffer.length > 1000, // Basic check
      timestamp: new Date().toISOString(),
    })
  } catch (err) {
    return NextResponse.json(
      { error: "Erro ao processar requisição", details: String(err) },
      { status: 500 }
    )
  }
}
