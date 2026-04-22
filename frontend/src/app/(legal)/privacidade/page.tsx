import type { Metadata } from "next"
import { Card, CardContent } from "@/components/ui/card"

export const metadata: Metadata = {
  title: "Politica de Privacidade",
  description: "Politica de Privacidade do DFeAxis - Compromisso com a protecao de dados pessoais conforme a LGPD.",
}

export default function PrivacidadePage() {
  return (
    <article className="print:text-black">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Politica de Privacidade</h1>
        <p className="text-sm text-muted-foreground">Ultima atualizacao: Abril 2026</p>
      </div>

      <Card>
        <CardContent className="prose prose-sm prose-neutral dark:prose-invert max-w-none pt-6 space-y-8">
          <section>
            <h2 className="text-xl font-semibold mb-3">1. Introducao</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis, operado por <strong>LINKTI MANUTENCAO EM SISTEMAS DE INFORMATICA LTDA.</strong>, inscrita no CNPJ
              sob o n. <strong>24.455.871/0001-68</strong>, com sede na Rua Frei Caneca, 640, Consolacao, Sao Paulo/SP,
              CEP 01307-000, tem o compromisso com a protecao dos dados pessoais de seus usuarios,
              em conformidade com a Lei Geral de Protecao de Dados Pessoais (LGPD - Lei n. 13.709/2018).
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              Esta Politica de Privacidade descreve como coletamos, utilizamos, armazenamos
              e protegemos suas informacoes ao utilizar nossa plataforma.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">2. Dados Coletados</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">Coletamos os seguintes dados:</p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Dados cadastrais:</strong> nome, e-mail, CNPJ e razao social.</li>
              <li><strong>Documentos fiscais eletronicos:</strong> processados para entrega ao ERP, porem <strong>nao armazenados</strong> (politica de zero-retention).</li>
              <li><strong>Dados de navegacao:</strong> endereco IP, tipo de navegador, paginas acessadas e logs de acesso.</li>
              <li><strong>Certificado digital A1:</strong> enviado pelo usuario para autenticacao na SEFAZ, armazenado de forma criptografada.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">3. Dados Sensiveis</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis <strong>nao coleta dados pessoais sensiveis</strong>, tais como informacoes
              sobre raca, etnia, religiao, opiniao politica, saude, vida sexual, dados geneticos
              ou biometricos, conforme definido no artigo 5, inciso II, da LGPD.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">4. Uso dos Dados</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">Os dados coletados sao utilizados para:</p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Prestacao do servico:</strong> captura e entrega de documentos fiscais eletronicos.</li>
              <li><strong>Suporte ao cliente:</strong> atendimento a duvidas, solicitacoes e resolucao de problemas.</li>
              <li><strong>Comunicacoes:</strong> notificacoes sobre o servico, atualizacoes e informacoes relevantes.</li>
              <li><strong>Analise de uso:</strong> melhoria continua da plataforma e da experiencia do usuario.</li>
              <li><strong>Compliance fiscal:</strong> cumprimento de obrigacoes legais e regulatorias.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">5. Certificado Digital</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O certificado digital A1 (.pfx) e criptografado com <strong>AES-256-GCM</strong>,
              com chave derivada por tenant. O certificado nunca e armazenado em texto claro.
              O acesso ao certificado e restrito ao processamento automatizado de captura
              de documentos fiscais, sem intervencao humana.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">6. Compartilhamento de Dados</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis <strong>nao vende, aluga ou comercializa</strong> dados pessoais de seus usuarios.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2 mb-2">
              Os dados podem ser compartilhados com os seguintes provedores de infraestrutura,
              estritamente para a operacao do servico:
            </p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Supabase:</strong> banco de dados e autenticacao.</li>
              <li><strong>Vercel:</strong> hospedagem do frontend.</li>
              <li><strong>Railway:</strong> hospedagem do backend.</li>
            </ul>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              Todos os provedores possuem politicas de privacidade proprias e estao em
              conformidade com padroes internacionais de seguranca.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">7. Retencao de Dados</h2>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Dados cadastrais:</strong> mantidos enquanto a conta estiver ativa. Apos exclusao da conta, os dados sao removidos em ate 30 dias.</li>
              <li><strong>Documentos fiscais:</strong> politica de <strong>zero-retention</strong>. Os XMLs sao descartados imediatamente apos a entrega ao ERP do cliente.</li>
              <li><strong>Logs de auditoria:</strong> mantidos por 90 (noventa) dias para fins de seguranca e compliance.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">8. Direitos do Titular (LGPD Art. 18)</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">
              Conforme a LGPD, voce tem os seguintes direitos sobre seus dados pessoais:
            </p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Confirmacao:</strong> confirmar a existencia de tratamento de seus dados.</li>
              <li><strong>Acesso:</strong> acessar seus dados pessoais tratados por nos.</li>
              <li><strong>Correcao:</strong> solicitar a correcao de dados incompletos, inexatos ou desatualizados.</li>
              <li><strong>Portabilidade:</strong> solicitar a portabilidade dos dados a outro fornecedor.</li>
              <li><strong>Eliminacao:</strong> solicitar a eliminacao de dados pessoais tratados com base no consentimento.</li>
            </ul>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              As solicitacoes serao atendidas em ate <strong>15 (quinze) dias uteis</strong>,
              conforme previsto na legislacao.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">9. Cookies</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis utiliza apenas <strong>cookies de sessao</strong> para fins de autenticacao
              e manutencao da sessao do usuario. Nao utilizamos cookies de rastreamento
              de terceiros, cookies publicitarios ou tecnologias de fingerprinting.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">10. Seguranca</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-2">
              Adotamos medidas tecnicas e organizacionais para proteger seus dados:
            </p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2">
              <li><strong>Criptografia AES-256-GCM</strong> para dados sensiveis (certificados digitais).</li>
              <li><strong>Row Level Security (RLS)</strong> no banco de dados para isolamento entre tenants.</li>
              <li><strong>Audit log</strong> de todas as operacoes criticas.</li>
              <li><strong>HTTPS</strong> em todas as comunicacoes.</li>
              <li><strong>Rate limiting</strong> para protecao contra abusos.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">11. Contato do Encarregado (DPO)</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Para exercer seus direitos, esclarecer duvidas ou realizar solicitacoes
              relacionadas a esta Politica de Privacidade e ao tratamento de seus dados pessoais,
              entre em contato com nosso Encarregado de Protecao de Dados (DPO):
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-2">
              E-mail:{" "}
              <a href="mailto:privacidade@dfeaxis.com.br" className="text-primary hover:underline">
                privacidade@dfeaxis.com.br
              </a>
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">12. Alteracoes nesta Politica</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              O DFeAxis pode atualizar esta Politica de Privacidade a qualquer momento.
              As alteracoes serao publicadas nesta pagina com a data da ultima atualizacao
              sempre visivel no topo do documento. Recomendamos a consulta periodica.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">13. Legislacao Aplicavel</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Esta Politica de Privacidade e regida pela legislacao brasileira, em especial:
            </p>
            <ul className="text-sm text-muted-foreground leading-relaxed list-disc pl-5 space-y-2 mt-2">
              <li><strong>LGPD</strong> - Lei Geral de Protecao de Dados Pessoais (Lei n. 13.709/2018).</li>
              <li><strong>Marco Civil da Internet</strong> (Lei n. 12.965/2014).</li>
            </ul>
          </section>

          <section className="border-t pt-6">
            <h2 className="text-xl font-semibold mb-3">Contato</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Em caso de duvidas sobre esta Politica de Privacidade, entre em contato pelo e-mail{" "}
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
