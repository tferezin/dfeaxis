import type { Metadata } from "next"
import { Card, CardContent } from "@/components/ui/card"

export const metadata: Metadata = {
  title: "Termos de Uso",
  description: "Termos de Uso do DFeAxis — plataforma SaaS de captura automática de documentos fiscais eletrônicos.",
}

export default function TermosPage() {
  return (
    <article className="print:text-black">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Termos de Uso</h1>
        <p className="text-sm text-muted-foreground">Última atualização: Abril 2026</p>
      </div>

      <Card>
        <CardContent className="prose prose-sm prose-neutral dark:prose-invert max-w-none pt-6 space-y-8">
          <section>
            <h2 className="text-xl font-semibold mb-3">1. Aceitação dos Termos</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Ao acessar ou utilizar a plataforma DFeAxis, operada por <strong>LINKTI MANUTENÇÃO EM SISTEMAS DE INFORMÁTICA LTDA.</strong>,
              inscrita no CNPJ sob o n. <strong>24.455.871/0001-68</strong>, com sede na <strong>Rua Frei Caneca, 640, Consolação, São Paulo/SP, CEP 01307-000</strong>,
              você declara que leu, compreendeu e concorda integralmente com estes Termos de Uso.
              Caso não concorde com qualquer disposição, não utilize o serviço.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">2. Descrição do Serviço</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis é uma plataforma SaaS (Software as a Service) de captura automática de documentos fiscais
              eletrônicos (NF-e, CT-e, MDF-e, NFS-e) diretamente na SEFAZ, com entrega via API REST.
              O serviço é compatível com SAP DRC, TOTVS, Oracle e qualquer ERP que consuma APIs REST.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              O DFeAxis atua como intermediário técnico entre a SEFAZ e o sistema do cliente,
              automatizando a captura de documentos fiscais emitidos contra o CNPJ do usuário.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">3. Cadastro e Conta</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Para utilizar o DFeAxis, o usuário deve criar uma conta fornecendo informações verdadeiras,
              precisas e atualizadas. O usuário é integralmente responsável pela confidencialidade de
              sua senha e por todas as atividades realizadas em sua conta.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              A licença concedida ao usuário é não exclusiva, intransferível e revogável,
              limitada ao uso da plataforma conforme estes Termos.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">4. Planos e Pagamento</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis oferece planos mensais e anuais, com pagamento via PIX.
              Os créditos são pré-pagos e utilizados para a captura de documentos fiscais.
              O detalhamento dos planos, valores e quantidade de créditos está disponível
              na página de preços da plataforma.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              O não pagamento dentro do prazo estabelecido poderá resultar na suspensão
              temporária do acesso até a regularização.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">5. Trial Gratuito</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis oferece um período de teste gratuito de 7 (sete) dias, sem necessidade
              de cadastro de forma de pagamento. Durante o trial, o usuário tem acesso a todas
              as funcionalidades da plataforma.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              Após o término do período de teste, o acesso será bloqueado até que um plano
              seja contratado e o pagamento confirmado.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">6. Cancelamento</h2>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li>
                <strong>Plano mensal:</strong> pode ser cancelado a qualquer momento, sem multa.
                O acesso permanece ativo até o fim do período já pago.
              </li>
              <li>
                <strong>Plano anual (pago à vista):</strong> cancelamento com reembolso integral
                em até 7 (sete) dias após a contratação. Após esse prazo, não há reembolso,
                e o acesso permanece ativo até o fim da vigência.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">7. Certificado Digital</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O certificado digital A1 (.pfx) enviado pelo usuário é criptografado com
              AES-256-GCM, com chave derivada por tenant. O certificado <strong>nunca</strong> é
              armazenado em texto claro. Há isolamento total entre tenants, garantindo
              que nenhum usuário tenha acesso ao certificado de outro.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">8. Zero-Retention</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Os XMLs de documentos fiscais capturados são entregues ao ERP do cliente
              e imediatamente descartados. O DFeAxis <strong>não é um repositório</strong> de
              documentos fiscais e não armazena o conteúdo dos XMLs após a entrega.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">9. Obrigações do Usuário</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">O usuário se compromete a:</p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li>Não alterar, corromper, fazer engenharia reversa ou explorar vulnerabilidades da plataforma.</li>
              <li>Não utilizar o serviço para fins fraudulentos, ilegais ou em desacordo com a legislação vigente.</li>
              <li>Garantir que representantes ou colaboradores que acessem a plataforma em seu nome possuam a devida autorização.</li>
              <li>Manter seus dados cadastrais atualizados.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">10. Limitação de Responsabilidade</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis não se responsabiliza por danos decorrentes de uso indevido da plataforma,
              falhas causadas por terceiros (incluindo a SEFAZ), ou interrupções decorrentes de
              manutenção programada ou emergencial.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              O SLA (Service Level Agreement) de disponibilidade é de 99% (noventa e nove por cento)
              de uptime mensal, excluindo janelas de manutenção previamente comunicadas.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">11. Propriedade Intelectual</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Todo o conteúdo da plataforma, incluindo marca, logotipo, interface, código-fonte,
              documentação e materiais relacionados, é de propriedade exclusiva do DFeAxis
              e está protegido pelas leis de propriedade intelectual aplicáveis.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">12. Suspensão</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis reserva-se o direito de suspender ou encerrar o acesso do usuário,
              sem aviso prévio, em caso de descumprimento destes Termos, uso indevido
              da plataforma ou qualquer atividade que comprometa a segurança ou
              integridade do serviço.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">13. Alterações nos Termos</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis pode alterar estes Termos de Uso a qualquer momento.
              As alterações serão publicadas nesta página com a data de atualização.
              O uso continuado da plataforma após a publicação das alterações
              implica aceitação dos novos termos.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">14. Foro</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Para dirimir quaisquer controvérsias oriundas destes Termos, fica eleito o
              foro da comarca de <strong>São Paulo/SP</strong>, com exclusão de qualquer outro,
              por mais privilegiado que seja.
            </p>
          </section>

          <section className="border-t pt-6">
            <h2 className="text-xl font-semibold mb-3">Contato</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Em caso de dúvidas sobre estes Termos de Uso, entre em contato pelo e-mail{" "}
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
