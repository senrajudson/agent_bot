---
name: analyze
description: Use esta skill para analisar código, documentação, arquitetura, risco, comportamento ou causa raiz sem alterar arquivos e sem propor implementação final prematura.
---

## Objetivo

Fazer análise técnica antes de especificar, planejar ou implementar.

Use esta skill para:

- entender o estado atual do código;
- comparar documentação com implementação real;
- mapear fluxos;
- identificar causa raiz;
- levantar riscos;
- identificar acoplamentos;
- encontrar inconsistências;
- avaliar impacto antes de uma mudança.

## Regras

- Não alterar arquivos.
- Não implementar.
- Não criar tarefas.
- Não aplicar correções.
- Não executar comandos destrutivos.
- Não assumir que documentação está correta sem verificar o código.
- Não confundir hipótese com fato confirmado.
- Separar observação, inferência e recomendação.

## Saída obrigatória

Responder com:

1. Objetivo da análise.
2. Escopo analisado.
3. Arquivos/documentos consultados.
4. Fatos confirmados.
5. Hipóteses.
6. Riscos encontrados.
7. Inconsistências encontradas.
8. Impacto provável.
9. Recomendações.
10. Crie um pequeno parágrafo com o resumo do resultado.
11. Próxima etapa sugerida.

## Regras de classificação

Classificar cada achado como:

- confirmado no código;
- confirmado na documentação;
- inferido;
- pendente de verificação.

## Regra crítica

Esta etapa apenas analisa.
Não planejar implementação detalhada.
Não alterar arquivos.
