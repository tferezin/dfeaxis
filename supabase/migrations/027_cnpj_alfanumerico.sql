-- ============================================================
-- 027 — CNPJ alfanumerico (Reforma Tributaria, vigente jul/2026)
-- ============================================================
-- Motivacao:
--   A Receita Federal vai emitir CNPJ alfanumerico a partir de
--   01/julho/2026 (NT 2025.001). Formato: 14 caracteres, sendo as 12
--   primeiras posicoes em [A-Z0-9] e as 2 ultimas (digitos verificadores)
--   sempre numericas. CNPJs numericos atuais NAO sao convertidos —
--   coexistem com os novos no mesmo banco.
--
-- Mudanca:
--   Reescreve a funcao validate_cnpj() pra aceitar AMBOS os formatos.
--   - Numericos atuais: validam IDENTICO ao algoritmo anterior
--     (porque ascii('0')=48 -> 0, ascii('9')=57 -> 9, igual ao .::INTEGER).
--   - Alfanumericos novos: validam usando ascii(c) - 48 nas 12 primeiras
--     posicoes (ex: ascii('A')=65 -> 17, ascii('Z')=90 -> 42).
--
-- Compatibilidade:
--   - As constraints chk_certificates_cnpj e chk_documents_cnpj continuam
--     vigentes — apenas referenciam a funcao por nome, entao a redefinicao
--     pega automaticamente.
--   - Todos os CNPJs numericos ja inseridos continuam validos: o algoritmo
--     produz DV identico pros caracteres '0'-'9'.
--
-- Idempotente: CREATE OR REPLACE.
-- Reversibilidade: re-aplicar 003_security_hardening.sql restaura a versao
--   original (so-numerico).

CREATE OR REPLACE FUNCTION validate_cnpj(cnpj TEXT) RETURNS BOOLEAN AS $$
DECLARE
  weights_1 INTEGER[] := ARRAY[5,4,3,2,9,8,7,6,5,4,3,2];
  weights_2 INTEGER[] := ARRAY[6,5,4,3,2,9,8,7,6,5,4,3,2];
  sum_val INTEGER;
  remainder INTEGER;
  d1 INTEGER;
  d2 INTEGER;
  clean_cnpj TEXT;
  i INTEGER;
  char_val INTEGER;
BEGIN
  -- Remove formatacao (.- /espaco) e normaliza pra uppercase
  clean_cnpj := upper(regexp_replace(cnpj, '[.\-/[:space:]]', '', 'g'));

  -- Aceita 12 primeiras [A-Z0-9] + 2 ultimas (DV) numericas
  IF clean_cnpj !~ '^[A-Z0-9]{12}[0-9]{2}$' THEN
    RETURN FALSE;
  END IF;

  -- Rejeita CNPJs com todos os caracteres iguais (ex: 00000000000000)
  IF clean_cnpj ~ '^(.)\1{13}$' THEN
    RETURN FALSE;
  END IF;

  -- Algoritmo do DV: ascii(c) - 48
  -- - '0' (48) -> 0, '9' (57) -> 9 (idem ao algoritmo numerico antigo)
  -- - 'A' (65) -> 17, 'Z' (90) -> 42
  -- Numericos atuais validam IDENTICO ao comportamento anterior.

  -- Primeiro DV (posicao 13)
  sum_val := 0;
  FOR i IN 1..12 LOOP
    char_val := ascii(substring(clean_cnpj FROM i FOR 1)) - 48;
    sum_val := sum_val + char_val * weights_1[i];
  END LOOP;
  remainder := sum_val % 11;
  d1 := CASE WHEN remainder < 2 THEN 0 ELSE 11 - remainder END;

  IF substring(clean_cnpj FROM 13 FOR 1)::INTEGER != d1 THEN
    RETURN FALSE;
  END IF;

  -- Segundo DV (posicao 14)
  sum_val := 0;
  FOR i IN 1..13 LOOP
    char_val := ascii(substring(clean_cnpj FROM i FOR 1)) - 48;
    sum_val := sum_val + char_val * weights_2[i];
  END LOOP;
  remainder := sum_val % 11;
  d2 := CASE WHEN remainder < 2 THEN 0 ELSE 11 - remainder END;

  IF substring(clean_cnpj FROM 14 FOR 1)::INTEGER != d2 THEN
    RETURN FALSE;
  END IF;

  RETURN TRUE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION validate_cnpj(TEXT) IS
  'Valida CNPJ via mod 11. Aceita numerico tradicional (14 digitos) e alfanumerico (Reforma Tributaria 2026, 12 primeiras posicoes [A-Z0-9] + 2 DV numericos). Coexistencia: CNPJs numericos atuais validam identico ao algoritmo anterior porque ascii(0..9) - 48 == int(c).';
