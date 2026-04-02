import type { Metadata } from "next"
import { Card, CardContent } from "@/components/ui/card"

export const metadata: Metadata = {
  title: "Termos de Uso",
  description: "Termos de Uso do DFeAxis - Plataforma SaaS de captura automatica de documentos fiscais eletronicos.",
}

export default function TermosPage() {
  return (
    <article className="print:text-black">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Termos de Uso</h1>
        <p className="text-sm text-muted-foreground">Ultima atualizacao: Abril 2026</p>
      </div>

      <Card>
        <CardContent className="prose prose-sm prose-neutral dark:prose-invert max-w-none pt-6 space-y-8">
          <section>
            <h2 className="text-xl font-semibold mb-3">1. Aceitacao dos Termos</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Ao acessar ou utilizar a plataforma DFeAxis, operada por <strong>[RAZAO SOCIAL A DEFINIR]</strong>,
              inscrita no CNPJ sob o n. <strong>[CNPJ A DEFINIR]</strong>, com sede em <strong>[ENDERECO A DEFINIR]</strong>,
              voce declara que leu, compreendeu e concorda integralmente com estes Termos de Uso.
              Caso nao concorde com qualquer disposicao, nao utilize o servico.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">2. Descricao do Servico</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis e uma plataforma SaaS (Software as a Service) de captura automatica de documentos fiscais
              eletronicos (NF-e, CT-e, MDF-e, NFS-e) diretamente na SEFAZ, com entrega via API REST.
              O servico e compativel com SAP DRC, TOTVS, Oracle e qualquer ERP que consuma APIs REST.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              O DFeAxis atua como intermediario tecnico entre a SEFAZ e o sistema do cliente,
              automatizando a captura de documentos fiscais emitidos contra o CNPJ do usuario.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">3. Cadastro e Conta</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Para utilizar o DFeAxis, o usuario deve criar uma conta fornecendo informacoes verdadeiras,
              precisas e atualizadas. O usuario e integralmente responsavel pela confidencialidade de
              sua senha e por todas as atividades realizadas em sua conta.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              A licenca concedida ao usuario e nao exclusiva, intransferivel e revogavel,
              limitada ao uso da plataforma conforme estes Termos.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">4. Planos e Pagamento</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis oferece planos mensais e anuais, com pagamento via PIX.
              Os creditos sao pre-pagos e utilizados para a captura de documentos fiscais.
              O detalhamento dos planos, valores e quantidade de creditos esta disponivel
              na pagina de precos da plataforma.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              O nao pagamento dentro do prazo estabelecido podera resultar na suspensao
              temporaria do acesso ate a regularizacao.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">5. Trial Gratuito</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis oferece um periodo de teste gratuito de 7 (sete) dias, sem necessidade
              de cadastro de forma de pagamento. Durante o trial, o usuario tem acesso a todas
              as funcionalidades da plataforma.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              Apos o termino do periodo de teste, o acesso sera bloqueado ate que um plano
              seja contratado e o pagamento confirmado.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">6. Cancelamento</h2>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li>
                <strong>Plano mensal:</strong> pode ser cancelado a qualquer momento, sem multa.
                O acesso permanece ativo ate o fim do periodo ja pago.
              </li>
              <li>
                <strong>Plano anual (pago a vista):</strong> cancelamento com reembolso integral
                em ate 7 (sete) dias apos a contratacao. Apos esse prazo, nao ha reembolso,
                e o acesso permanece ativo ate o fim da vigencia.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">7. Certificado Digital</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O certificado digital A1 (.pfx) enviado pelo usuario e criptografado com
              AES-256-GCM, com chave derivada por tenant. O certificado <strong>nunca</strong> e
              armazenado em texto claro. Ha isolamento total entre tenants, garantindo
              que nenhum usuario tenha acesso ao certificado de outro.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">8. Zero-Retention</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Os XMLs de documentos fiscais capturados sao entregues ao ERP do cliente
              e imediatamente descartados. O DFeAxis <strong>nao e um repositorio</strong> de
              documentos fiscais e nao armazena o conteudo dos XMLs apos a entrega.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">9. Obrigacoes do Usuario</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">O usuario se compromete a:</p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li>Nao alterar, corromper, fazer engenharia reversa ou explorar vulnerabilidades da plataforma.</li>
              <li>Nao utilizar o servico para fins fraudulentos, ilegais ou em desacordo com a legislacao vigente.</li>
              <li>Garantir que representantes ou colaboradores que acessem a plataforma em seu nome possuam a devida autorizacao.</li>
              <li>Manter seus dados cadastrais atualizados.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">10. Limitacao de Responsabilidade</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis nao se responsabiliza por danos decorrentes de uso indevido da plataforma,
              falhas causadas por terceiros (incluindo a SEFAZ), ou interrupcoes decorrentes de
              manutencao programada ou emergencial.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              O SLA (Service Level Agreement) de disponibilidade e de 99% (noventa e nove por cento)
              de uptime mensal, excluindo janelas de manutencao previamente comunicadas.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">11. Propriedade Intelectual</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Todo o conteudo da plataforma, incluindo marca, logotipo, interface, codigo-fonte,
              documentacao e materiais relacionados, sao de propriedade exclusiva do DFeAxis
              e estao protegidos pelas leis de propriedade intelectual aplicaveis.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">12. Suspensao</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis reserva-se o direito de suspender ou encerrar o acesso do usuario,
              sem aviso previo, em caso de descumprimento destes Termos, uso indevido
              da plataforma ou qualquer atividade que comprometa a seguranca ou
              integridade do servico.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">13. Alteracoes nos Termos</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis pode alterar estes Termos de Uso a qualquer momento.
              As alteracoes serao publicadas nesta pagina com a data de atualizacao.
              O uso continuado da plataforma apos a publicacao das alteracoes
              implica aceitacao dos novos termos.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">14. Foro</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Para dirimir quaisquer controversias oriundas destes Termos, fica eleito o
              foro da comarca de <strong>[FORO A DEFINIR]</strong>, com exclusao de qualquer outro,
              por mais privilegiado que seja.
            </p>
          </section>

          <section className="border-t pt-6">
            <h2 className="text-xl font-semibold mb-3">Contato</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Em caso de duvidas sobre estes Termos de Uso, entre em contato pelo e-mail{" "}
              <a href="mailto:contato@dfeaxis.com.br" className="text-primary hover:underline">
                contato@dfeaxis.com.br
              </a>.
            </p>
          </section>
        </CardContent>
      </Card>
    </article>
  )
}
