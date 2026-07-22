---
name: tasks
description: Use esta skill para quebrar um plano aprovado em tarefas pequenas, sequenciais e verificáveis, sem executar nenhuma delas.
---

## Objetivo

Transformar um plano aprovado em tarefas executáveis pequenas.

## Regras

- Não alterar arquivos.
- Não implementar tarefas.
- Não executar comandos.
- Não corrigir código.
- Não criar arquivos.
- Não juntar várias mudanças em uma tarefa grande.
- Cada tarefa deve ser pequena, revisável e reversível.

## Saída obrigatória

Para cada tarefa, responder com:

1. ID
2. Nome
3. Objetivo
4. Arquivos permitidos
5. Arquivos proibidos
6. Passos
7. Critério de aceite
8. Testes/checks
9. Risco

## Regra crítica

A etapa `tasks` nunca executa nada.
Ela apenas gera a lista de tarefas.
