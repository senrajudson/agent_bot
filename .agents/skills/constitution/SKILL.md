---
name: constitution
description: Use esta skill para criar, revisar ou atualizar o arquivo Markdown de governança do projeto, mantendo regras, princípios, restrições e workflow alinhados ao código real.
---

## Objetivo

Manter o arquivo Markdown de governança do projeto atualizado, claro e aplicável.

Esta skill não serve para implementar código.
Esta skill serve para orientar a criação, revisão ou atualização de documentos como:

- `AGENTS.md`
- `CONSTITUTION.md`
- `.specify/memory/constitution.md`
- documentação de governança equivalente definida pelo usuário

## Regras

- Não alterar código de aplicação.
- Não alterar comportamento funcional.
- Não alterar prompts de LLM do produto.
- Não alterar integrações.
- Não declarar uma regra como obrigatória se ela ainda não foi aprovada pelo usuário.
- Não documentar arquitetura desejada como se já estivesse implementada.
- Diferenciar:
  - regra obrigatória;
  - recomendação;
  - dívida técnica;
  - decisão pendente;
  - prática futura.

## Responsabilidade principal

Ao atualizar o arquivo Markdown de governança, garantir que ele contenha:

1. Princípios arquiteturais.
2. Restrições de alteração em ambiente sensível.
3. Workflow obrigatório do agente.
4. Regras de aprovação antes de editar código.
5. Regras para `/specify`, `/clarify`, `/plan`, `/tasks`, `/checklist`, `/implement` e `/validate`.
6. Regras de documentação.
7. Regras de testes/checks.
8. Regras de escopo proibido.
9. Critérios para considerar uma tarefa concluída.
10. Registro de impactos da mudança no próprio documento.

## Workflow obrigatório

Antes de atualizar qualquer arquivo Markdown:

1. Identificar qual documento será atualizado.
2. Explicar por que a atualização é necessária.
3. Listar as seções que serão alteradas.
4. Informar se a mudança é:
   - nova regra;
   - correção de inconsistência;
   - reorganização;
   - remoção de regra obsoleta;
   - esclarecimento de regra existente.
5. Aguardar confirmação explícita do usuário.

## Regras sobre o conteúdo

O documento de governança deve enfatizar:

- `/tasks` nunca executa tarefas.
- `/plan` nunca altera código.
- `/specify` nunca propõe implementação detalhada.
- `/implement` só executa tarefa aprovada.
- `/validate` não corrige automaticamente.
- mudanças devem ser pequenas, revisáveis e reversíveis.
- código fora do escopo não deve ser alterado.
- documentação deve refletir o código real.
- arquitetura ideal deve ser marcada como plano, não como estado atual.

## Saída obrigatória

Responder com:

1. Documento alvo.
2. Motivo da atualização.
3. Seções afetadas.
4. Resumo da mudança proposta.
5. Riscos da mudança.
6. Confirmação necessária antes de editar.

## Ao finalizar

Responder com:

1. Arquivo Markdown alterado.
2. Seções modificadas.
3. Regras adicionadas.
4. Regras removidas.
5. Inconsistências corrigidas.
6. Pendências ou decisões futuras.
