---
name: implement
description: Use esta skill para implementar somente uma tarefa previamente aprovada, com escopo mínimo e sem alterações oportunistas.
---

## Objetivo

Executar uma única tarefa aprovada.

## Regras

- Implementar somente a tarefa aprovada.
- Não executar tarefas futuras.
- Não alterar arquivos fora da lista permitida.
- Não fazer limpeza geral.
- Não refatorar código não relacionado.
- Não alterar comportamento além do definido.
- Não alterar contratos públicos sem autorização.
- Não alterar prompts, integrações, Docker ou infraestrutura sem autorização.
- Parar e pedir confirmação se encontrar problema fora do escopo.

## Antes de alterar arquivos

Responder primeiro com:

1. Tarefa que será executada
2. Arquivos que serão alterados
3. Mudança exata prevista
4. Risco
5. Confirmação necessária

## Ao finalizar

Responder com:

1. Arquivos alterados
2. Resumo do diff
3. O que foi preservado
4. Testes/checks executados
5. Pendências
