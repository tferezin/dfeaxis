import path from "node:path";
import type { NextConfig } from "next";

const projectRoot = path.resolve(__dirname);

// Item M8: headers de seguranca aplicados a todas as rotas do frontend.
// CSP cobre o que o app efetivamente usa (Stripe, GA, Supabase). Se um
// novo provider for integrado, adicionar dominio aqui em script-src/
// connect-src/frame-src.
const SECURITY_HEADERS = [
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value:
      "camera=(), microphone=(), geolocation=(), payment=(), usb=(), magnetometer=(), accelerometer=(), gyroscope=()",
  },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // unsafe-inline em script-src e exigido pelo GTM/GA + bootstrap
      // inline da Clarity. Migrar pra nonce-based CSP num passo futuro.
      "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://js.stripe.com https://challenges.cloudflare.com https://www.clarity.ms",
      // connect-src cobre XHR/fetch — clarity.ms uploads de sessao usam
      // wildcard subdomain (*.clarity.ms = b.clarity.ms etc).
      "connect-src 'self' https://*.supabase.co https://*.supabase.in https://api.stripe.com https://www.google-analytics.com https://region1.google-analytics.com https://challenges.cloudflare.com https://*.clarity.ms https://www.clarity.ms",
      "frame-src https://js.stripe.com https://hooks.stripe.com https://challenges.cloudflare.com",
      "img-src 'self' data: https: blob:",
      // Google Fonts CSS vem de fonts.googleapis.com (stylesheet externo).
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      // Arquivos .woff2 das Fonts vem de fonts.gstatic.com.
      "font-src 'self' data: https://fonts.gstatic.com",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self' https://checkout.stripe.com",
      "frame-ancestors 'none'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  // Pin Turbopack workspace root to this dir (avoids picking up parent
  // lockfiles in $HOME and getting stuck on "Starting...").
  turbopack: {
    root: projectRoot,
  },
  // Next.js 16 exige que outputFileTracingRoot seja igual a turbopack.root
  // pra evitar warning em build.
  outputFileTracingRoot: projectRoot,
  // Serve a landing estática em `/` sem expor o nome do arquivo na barra.
  // V4 é a landing oficial (decidido em 22/04/2026). A V3 continua
  // acessível via /landing-v3.html direto pra comparação/rollback rápido.
  async rewrites() {
    return [
      {
        source: "/",
        destination: "/landing-v4.html",
      },
    ]
  },
  async headers() {
    return [
      {
        // Aplica em todas as rotas (incluindo /landing-v4.html servido via rewrite).
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

export default nextConfig;
