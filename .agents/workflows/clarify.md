---
description: Executa exclusivamente a skill clarify para identificar ambiguidades, decisões pendentes, riscos e perguntas necessárias antes de planejar ou implementar.
---

# Clarify

Quando este workflow for invocado com `/clarify`, execute exclusivamente a skill localizada em:

`.agents/skills/clarify/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/clarify/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a etapa de clarificação definida nessa skill.
4. Use como contexto a análise, especificação, documentação, código, decisão anterior ou solicitação fornecida pelo usuário.
5. Caso nenhuma fonte seja explicitamente indicada, utilize o contexto atual da conversa.
6. Consulte o código ou documentação disponível quando isso permitir resolver uma dúvida com segurança sem perguntar ao usuário.
7. Não transforme uma hipótese em decisão confirmada.
8. Priorize apenas ambiguidades que possam alterar:
   - escopo;
   - comportamento;
   - arquitetura;
   - compatibilidade;
   - segurança;
   - risco operacional;
   - critérios de aceite;
   - estratégia de implementação.
9. Produza a resposta conforme a seção "Saída obrigatória" da skill `clarify`.

## Restrições

Durante esta execução:

- Não executar outras skills.
- Não executar outros workflows.
- Não iniciar `/analyze`.
- Não iniciar `/specify`.
- Não iniciar `/planning` ou `/plan`.
- Não iniciar `/tasks`.
- Não iniciar `/implement`.
- Não iniciar `/validate`.
- Não alterar arquivos.
- Não criar arquivos.
- Não implementar código.
- Não aplicar correções.
- Não criar tarefas.
- Não criar plano técnico detalhado.
- Não assumir decisões críticas sem confirmação.
- Não avançar automaticamente para outra etapa.

## Tratamento de ambiguidades

Antes de criar uma pergunta, determine se a resposta pode ser obtida com segurança por meio de:

- código existente;
- configuração atual;
- testes;
- documentação;
- especificações já aprovadas;
- decisões anteriores presentes no contexto;
- comportamento comprovável do sistema.

Se a resposta puder ser determinada com segurança por essas fontes, registre-a como uma suposição segura ou fato confirmado e não pergunte ao usuário.

Se existirem fontes conflitantes, registre a divergência como uma ambiguidade.

## Classificação das perguntas

### Perguntas obrigatórias

Considere obrigatória uma pergunta quando diferentes respostas possam produzir mudanças relevantes em:

- arquitetura;
- comportamento funcional;
- compatibilidade;
- modelo de dados;
- interfaces;
- segurança;
- risco de produção;
- escopo da mudança;
- critérios de aceite.

Perguntas obrigatórias devem ser respondidas antes de planejamento ou implementação.

### Perguntas opcionais

Considere opcional uma pergunta quando sua resposta puder melhorar a solução, mas não impedir uma decisão técnica segura.

Não transforme preferências secundárias em bloqueadores.

## Regra de decisão

Não pergunte:

- informações já confirmadas;
- detalhes que podem ser inferidos com segurança;
- preferências irrelevantes para a mudança;
- decisões que não alteram escopo, comportamento, arquitetura ou risco.

Prefira poucas perguntas relevantes a uma lista extensa de dúvidas genéricas.

## Quando não houver ambiguidades

Se nenhuma ambiguidade relevante for encontrada:

1. Informe explicitamente que não existem questões bloqueantes.
2. Registre as suposições seguras utilizadas.
3. Informe a próxima etapa recomendada.
4. Não invente perguntas apenas para preencher a estrutura.

## Quando houver perguntas obrigatórias

Se existirem perguntas obrigatórias:

1. Apresente todas as seções exigidas pela skill.
2. Destaque claramente quais decisões estão bloqueadas.
3. Faça as perguntas necessárias ao usuário.
4. Encerre a execução aguardando as respostas.

Não avance para planejamento ou implementação enquanto houver decisões obrigatórias pendentes.

## Regra crítica

Este workflow termina quando:

- as ambiguidades relevantes foram identificadas;
- as decisões necessárias foram explicitadas;
- os riscos foram registrados;
- as perguntas realmente necessárias foram apresentadas;
- as suposições seguras foram documentadas.

Se houver perguntas obrigatórias, aguarde a resposta do usuário.

Não planejar.

Não implementar.

Não alterar arquivos.

Não avançar automaticamente para outra etapa.