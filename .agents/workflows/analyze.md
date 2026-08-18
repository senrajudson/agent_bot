---
description: Executa exclusivamente a skill analyze para realizar análise técnica sem alterar arquivos, implementar, planejar ou criar tarefas.
---

# Analyze

Quando este workflow for invocado com `/analyze`, execute exclusivamente a skill localizada em:

`.agents/skills/analyze/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/analyze/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a etapa de análise definida nessa skill.
4. Use como objeto da análise qualquer contexto ou solicitação fornecida pelo usuário após `/analyze`.
5. Caso nenhum contexto adicional seja fornecido, utilize o contexto atual da conversa para determinar o objeto da análise.
6. Consulte apenas os arquivos, documentação, código e informações necessários para cumprir a análise.
7. Produza a saída exatamente conforme a seção "Saída obrigatória" da skill `analyze`.

## Restrições

Durante esta execução:

- Não executar outras skills.
- Não executar outros workflows.
- Não iniciar `/specify`.
- Não iniciar `/clarify`.
- Não iniciar `/planning` ou `/plan`.
- Não iniciar `/tasks`.
- Não iniciar `/implement`.
- Não iniciar `/validate`.
- Não alterar arquivos.
- Não criar arquivos.
- Não implementar código.
- Não aplicar correções.
- Não criar tarefas.
- Não produzir plano detalhado de implementação.
- Não avançar automaticamente para a próxima etapa.

A seção "Próxima etapa sugerida" da skill deve apenas informar qual seria a próxima etapa apropriada, sem executá-la.

## Regra crítica

Este workflow termina quando a análise e sua saída obrigatória forem concluídas.

Não encadear nenhuma outra etapa automaticamente.