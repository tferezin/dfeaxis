import type { Metadata } from "next"
import { Inter } from "next/font/google"
import Script from "next/script"
import { AttributionCapture } from "@/components/attribution-capture"
import { Toaster } from "@/components/ui/sonner"
import "./globals.css"

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: {
    default: "DFeAxis",
    template: "%s | DFeAxis",
  },
  description: "Captura automática de documentos fiscais da SEFAZ. API REST para SAP DRC, TOTVS, Oracle e qualquer ERP. Trial grátis.",
}

// IDs mantidos em sync com frontend/public/landing-v3.html (bloco DFEAXIS_TRACKING).
// Quando for rotacionar/trocar ID, atualize nos dois lugares.
const GA4_ID = "G-XZTRG63C53"
const CLARITY_ID = "wb36mtmtue"
const GTM_ID = process.env.NEXT_PUBLIC_GTM_ID || "GTM-PLACEHOLDER"
const META_PIXEL_ID = process.env.NEXT_PUBLIC_META_PIXEL_ID || "PIXEL_PLACEHOLDER"

const isReal = (v: string) => v && !v.includes("PLACEHOLDER")

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        {/* Google Analytics 4 */}
        {isReal(GA4_ID) && (
          <>
            <Script
              id="ga4-loader"
              strategy="afterInteractive"
              src={`https://www.googletagmanager.com/gtag/js?id=${GA4_ID}`}
            />
            <Script id="ga4-init" strategy="afterInteractive">
              {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
window.gtag = gtag;
gtag('js', new Date());
gtag('config', '${GA4_ID}', { send_page_view: true });`}
            </Script>
          </>
        )}
        {/* Microsoft Clarity */}
        {isReal(CLARITY_ID) && (
          <Script id="clarity" strategy="afterInteractive">
            {`(function(c,l,a,r,i,t,y){
c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
})(window, document, "clarity", "script", "${CLARITY_ID}");`}
          </Script>
        )}
        {/* Google Tag Manager */}
        {isReal(GTM_ID) && (
          <Script id="gtm" strategy="afterInteractive">
            {`(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','${GTM_ID}');`}
          </Script>
        )}
        {/* Meta Pixel */}
        {isReal(META_PIXEL_ID) && (
          <Script id="meta-pixel" strategy="afterInteractive">
            {`!function(f,b,e,v,n,t,s)
{if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init','${META_PIXEL_ID}');
fbq('track','PageView');`}
          </Script>
        )}
      </head>
      <body className={`${inter.variable} font-sans antialiased`}>
        {isReal(GTM_ID) && (
          <noscript>
            <iframe
              src={`https://www.googletagmanager.com/ns.html?id=${GTM_ID}`}
              height="0"
              width="0"
              style={{ display: "none", visibility: "hidden" }}
            />
          </noscript>
        )}
        {isReal(META_PIXEL_ID) && (
          <noscript>
            <img
              height="1"
              width="1"
              style={{ display: "none" }}
              src={`https://www.facebook.com/tr?id=${META_PIXEL_ID}&ev=PageView&noscript=1`}
              alt=""
            />
          </noscript>
        )}
        <AttributionCapture />
        {children}
        <Toaster />
      </body>
    </html>
  )
}
