---
description: Executa exclusivamente a skill checklist para criar ou atualizar checklists verificáveis sem implementar, alterar código ou executar tarefas.
---

# Checklist

Quando este workflow for invocado com `/checklist`, execute exclusivamente a skill localizada em:

`.agents/skills/checklist/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/checklist/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a etapa de checklist definida nessa skill.
4. Use como fonte a especificação, plano, tarefa, documentação ou contexto fornecido pelo usuário.
5. Caso nenhum artefato seja explicitamente informado, utilize o contexto atual da conversa para identificar a fonte do checklist.
6. Não invente requisitos que não estejam sustentados pelo contexto analisado.
7. Quando houver informação insuficiente para tornar um item verificável, identifique essa limitação no próprio checklist.
8. Organize o checklist pelas categorias definidas na skill quando elas forem aplicáveis.
9. Produza cada item exatamente no formato obrigatório definido pela skill `checklist`.

## Restrições

Durante esta execução:

- Não executar outras skills.
- Não executar outros workflows.
- Não iniciar `/analyze`.
- Não iniciar `/specify`.
- Não iniciar `/clarify`.
- Não iniciar `/planning` ou `/plan`.
- Não iniciar `/tasks`.
- Não iniciar `/implement`.
- Não iniciar `/validate`.
- Não alterar arquivos.
- Não alterar código.
- Não implementar.
- Não executar tarefas.
- Não aplicar correções.
- Não criar um novo plano técnico.
- Não avançar automaticamente para outra etapa.

## Tratamento da fonte

O checklist deve ser derivado exclusivamente das informações disponíveis na fonte utilizada.

Quando houver múltiplas fontes, como:

- especificação;
- plano;
- tasks;
- documentação;
- contexto da conversa;

considere todas elas, mas não transforme divergências em requisitos implícitos.

Se houver inconsistências entre as fontes, registre um item de verificação específico para confirmar qual regra deve prevalecer.

## Regra de verificabilidade

Cada item criado deve representar uma condição que possa ser objetivamente verificada.

Evite itens como:

`[ ] Verificar se está tudo correto`

Prefira itens como:

`[ ] Confirmar que o valor default de MCP_SERIES_CSV_RECORDED_MAX_COUNT é 150000`
  - evidência esperada: configuração contendo o valor default 150000
  - arquivo/comando relacionado: arquivo de configuração correspondente
  - obrigatório: sim

## Regra crítica

Este workflow termina quando o checklist solicitado estiver criado ou atualizado.

Não executar nenhum item do checklist.

Não implementar.

Não alterar código.

Não avançar automaticamente para outra etapa.