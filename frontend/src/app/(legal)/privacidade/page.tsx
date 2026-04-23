import type { Metadata } from "next"
import { Card, CardContent } from "@/components/ui/card"

export const metadata: Metadata = {
  title: "Política de Privacidade",
  description: "Política de Privacidade do DFeAxis — compromisso com a proteção de dados pessoais conforme a LGPD.",
}

export default function PrivacidadePage() {
  return (
    <article className="print:text-black">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Política de Privacidade</h1>
        <p className="text-sm text-muted-foreground">Última atualização: Abril 2026</p>
      </div>

      <Card>
        <CardContent className="prose prose-sm prose-neutral dark:prose-invert max-w-none pt-6 space-y-8">
          <section>
            <h2 className="text-xl font-semibold mb-3">1. Introdução</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis, operado por <strong>LINKTI MANUTENÇÃO EM SISTEMAS DE INFORMÁTICA LTDA.</strong>, inscrita no CNPJ
              sob o n. <strong>24.455.871/0001-68</strong>, com sede na Rua Frei Caneca, 640, Consolação, São Paulo/SP,
              CEP 01307-000, tem o compromisso com a proteção dos dados pessoais de seus usuários,
              em conformidade com a Lei Geral de Proteção de Dados Pessoais (LGPD — Lei n. 13.709/2018).
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              Esta Política de Privacidade descreve como coletamos, utilizamos, armazenamos
              e protegemos suas informações ao utilizar nossa plataforma.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">2. Dados Coletados</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">Coletamos os seguintes dados:</p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Dados cadastrais:</strong> nome, e-mail, CNPJ e razão social.</li>
              <li><strong>Documentos fiscais eletrônicos:</strong> processados para entrega ao ERP, porém <strong>não armazenados</strong> (política de zero-retention).</li>
              <li><strong>Dados de navegação:</strong> endereço IP, tipo de navegador, páginas acessadas e logs de acesso.</li>
              <li><strong>Certificado digital A1:</strong> enviado pelo usuário para autenticação na SEFAZ, armazenado de forma criptografada.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">3. Dados Sensíveis</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis <strong>não coleta dados pessoais sensíveis</strong>, tais como informações
              sobre raça, etnia, religião, opinião política, saúde, vida sexual, dados genéticos
              ou biométricos, conforme definido no artigo 5, inciso II, da LGPD.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">4. Uso dos Dados</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">Os dados coletados são utilizados para:</p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Prestação do serviço:</strong> captura e entrega de documentos fiscais eletrônicos.</li>
              <li><strong>Suporte ao cliente:</strong> atendimento a dúvidas, solicitações e resolução de problemas.</li>
              <li><strong>Comunicações:</strong> notificações sobre o serviço, atualizações e informações relevantes.</li>
              <li><strong>Análise de uso:</strong> melhoria contínua da plataforma e da experiência do usuário.</li>
              <li><strong>Compliance fiscal:</strong> cumprimento de obrigações legais e regulatórias.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">5. Certificado Digital</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O certificado digital A1 (.pfx) é criptografado com <strong>AES-256-GCM</strong>,
              com chave derivada por tenant. O certificado nunca é armazenado em texto claro.
              O acesso ao certificado é restrito ao processamento automatizado de captura
              de documentos fiscais, sem intervenção humana.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">6. Compartilhamento de Dados</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis <strong>não vende, aluga ou comercializa</strong> dados pessoais de seus usuários.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2 mb-2">
              Os dados podem ser compartilhados com os seguintes provedores de infraestrutura,
              estritamente para a operação do serviço:
            </p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Supabase:</strong> banco de dados e autenticação.</li>
              <li><strong>Vercel:</strong> hospedagem do frontend.</li>
              <li><strong>Railway:</strong> hospedagem do backend.</li>
            </ul>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              Todos os provedores possuem políticas de privacidade próprias e estão em
              conformidade com padrões internacionais de segurança.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">7. Retenção de Dados</h2>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Dados cadastrais:</strong> mantidos enquanto a conta estiver ativa. Após exclusão da conta, os dados são removidos em até 30 dias.</li>
              <li><strong>Documentos fiscais:</strong> política de <strong>zero-retention</strong>. Os XMLs são descartados imediatamente após a entrega ao ERP do cliente.</li>
              <li><strong>Logs de auditoria:</strong> mantidos por 90 (noventa) dias para fins de segurança e compliance.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">8. Direitos do Titular (LGPD Art. 18)</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">
              Conforme a LGPD, você tem os seguintes direitos sobre seus dados pessoais:
            </p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Confirmação:</strong> confirmar a existência de tratamento de seus dados.</li>
              <li><strong>Acesso:</strong> acessar seus dados pessoais tratados por nós.</li>
              <li><strong>Correção:</strong> solicitar a correção de dados incompletos, inexatos ou desatualizados.</li>
              <li><strong>Portabilidade:</strong> solicitar a portabilidade dos dados a outro fornecedor.</li>
              <li><strong>Eliminação:</strong> solicitar a eliminação de dados pessoais tratados com base no consentimento.</li>
            </ul>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              As solicitações serão atendidas em até <strong>15 (quinze) dias úteis</strong>,
              conforme previsto na legislação.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">9. Cookies</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis utiliza apenas <strong>cookies de sessão</strong> para fins de autenticação
              e manutenção da sessão do usuário. Não utilizamos cookies de rastreamento
              de terceiros, cookies publicitários ou tecnologias de fingerprinting.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">10. Segurança</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">
              Adotamos medidas técnicas e organizacionais para proteger seus dados:
            </p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Criptografia AES-256-GCM</strong> para dados sensíveis (certificados digitais).</li>
              <li><strong>Row Level Security (RLS)</strong> no banco de dados para isolamento entre tenants.</li>
              <li><strong>Audit log</strong> de todas as operações críticas.</li>
              <li><strong>HTTPS</strong> em todas as comunicações.</li>
              <li><strong>Rate limiting</strong> para proteção contra abusos.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">11. Contato do Encarregado (DPO)</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Para exercer seus direitos, esclarecer dúvidas ou realizar solicitações
              relacionadas a esta Política de Privacidade e ao tratamento de seus dados pessoais,
              entre em contato com nosso Encarregado de Proteção de Dados (DPO):
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              E-mail:{" "}
              <a href="mailto:privacidade@dfeaxis.com.br" className="text-primary hover:underline">
                privacidade@dfeaxis.com.br
              </a>
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">12. Alterações nesta Política</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis pode atualizar esta Política de Privacidade a qualquer momento.
              As alterações serão publicadas nesta página com a data da última atualização
              sempre visível no topo do documento. Recomendamos a consulta periódica.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">13. Legislação Aplicável</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Esta Política de Privacidade é regida pela legislação brasileira, em especial:
            </p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2 mt-2">
              <li><strong>LGPD</strong> — Lei Geral de Proteção de Dados Pessoais (Lei n. 13.709/2018).</li>
              <li><strong>Marco Civil da Internet</strong> (Lei n. 12.965/2014).</li>
            </ul>
          </section>

          <section className="border-t pt-6">
            <h2 className="text-xl font-semibold mb-3">Contato</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Em caso de dúvidas sobre esta Política de Privacidade, entre em contato pelo e-mail{" "}
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
