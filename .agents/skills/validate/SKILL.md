---
name: validate
description: Use esta skill para validar uma mudança aplicada, revisar diff, executar testes e comparar com critérios de aceite.
---

## Objetivo

Validar se uma mudança implementada atende ao combinado sem quebrar comportamento existente.

## Regras

- Não implementar novas mudanças.
- Não corrigir falhas sem confirmação.
- Não alterar arquivos durante a validação.
- Não ampliar o escopo.
- Separar erro real de melhoria opcional.

## Validações esperadas

Verificar:

1. Arquivos alterados
2. Diff resumido
3. Critérios de aceite
4. Testes executados
5. Resultado dos testes
6. Riscos restantes
7. Regressões potenciais
8. Documentação afetada
9. Próxima ação recomendada

## Regra crítica

Se encontrar problema, reportar.
Não corrigir automaticamente.
