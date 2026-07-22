---
name: checklist
description: Use esta skill para criar checklist de validação ou execução a partir de uma especificação, plano ou tarefa, sem implementar nada.
---

## Objetivo

Criar checklists objetivos para controlar qualidade, escopo, segurança e aceite.

Use esta skill para gerar:

- checklist de pré-implementação;
- checklist de revisão;
- checklist de validação;
- checklist de regressão;
- checklist de documentação;
- checklist de deploy;
- checklist de aderência à governança.

## Regras

- Não alterar arquivos.
- Não implementar.
- Não executar tarefas.
- Não corrigir problemas.
- Não criar plano técnico novo.
- O checklist deve ser verificável.
- Cada item deve poder ser marcado como feito ou não feito.
- Evitar itens genéricos demais.

## Tipos de checklist

Quando fizer sentido, separar em:

1. Escopo.
2. Arquitetura.
3. Código.
4. Testes.
5. Documentação.
6. Segurança operacional.
7. Compatibilidade.
8. Observabilidade.
9. Rollback.
10. Critérios de aceite.

## Formato obrigatório

Cada item deve seguir este formato:

- `[ ]` descrição do item
  - evidência esperada:
  - arquivo/comando relacionado:
  - obrigatório: sim/não

## Regra crítica

A etapa `checklist` apenas cria ou atualiza checklist.
Não implementar.
Não alterar código.
Não executar tarefas.