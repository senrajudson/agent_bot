---
description: Executa exclusivamente a skill specify para transformar uma solicitação em uma especificação clara, delimitada e verificável, sem planejar implementação, criar tarefas ou alterar arquivos.
---

# Specify

Quando este workflow for invocado com `/specify`, execute exclusivamente a skill localizada em:

`.agents/skills/specify/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/specify/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a etapa de especificação definida nessa skill.
4. Utilize como fonte, quando disponíveis:
   - solicitação atual do usuário;
   - contexto da conversa;
   - análise anterior;
   - documentação relevante;
   - comportamento atual confirmado;
   - decisões já aprovadas.
5. Transforme a solicitação em requisitos objetivos e verificáveis.
6. Preserve estritamente o escopo solicitado.
7. Diferencie claramente:
   - requisito confirmado;
   - restrição;
   - sugestão técnica;
   - hipótese;
   - ambiguidade.
8. Não transforme sugestões técnicas em requisitos sem fundamento.
9. Não invente comportamento esperado que não tenha sido solicitado ou confirmado.
10. Produza a resposta conforme a seção "Saída obrigatória" da skill `specify`.

## Restrições

Durante esta execução:

- Não executar outras skills.
- Não executar outros workflows.
- Não iniciar `/analyze`.
- Não iniciar `/clarify`.
- Não iniciar `/planning`.
- Não iniciar `/plan`.
- Não iniciar `/tasks`.
- Não iniciar `/checklist`.
- Não iniciar `/implement`.
- Não iniciar `/validate`.
- Não alterar arquivos.
- Não criar arquivos.
- Não modificar código.
- Não implementar.
- Não criar tarefas.
- Não criar plano técnico detalhado.
- Não definir implementação final.
- Não ampliar o escopo.
- Não introduzir requisitos não sustentados pela solicitação ou contexto.
- Não avançar automaticamente para outra etapa.

# Preparação da especificação

Antes de produzir a especificação:

1. Identifique a solicitação central do usuário.
2. Determine qual problema precisa ser resolvido.
3. Identifique o resultado esperado.
4. Identifique as restrições explicitamente fornecidas.
5. Identifique comportamentos atuais que precisam ser preservados.
6. Determine o que pertence ao escopo.
7. Determine o que deve permanecer fora do escopo.
8. Identifique ambiguidades que possam impedir uma especificação completa.

## Fonte de verdade

Utilize como prioridade:

1. Decisões explícitas do usuário.
2. Comportamento confirmado no código ou sistema.
3. Documentação vigente e compatível com o comportamento real.
4. Contexto anterior da conversa.
5. Inferências seguras claramente identificadas.

Se houver conflito entre essas fontes, não escolha silenciosamente uma delas.

Registre o conflito em `Ambiguidades`.

Não documente como requisito confirmado algo que ainda dependa de decisão.

# Objetivo

O objetivo deve explicar:

- qual problema será tratado;
- qual resultado se espera obter;
- sem explicar ainda como tecnicamente será implementado.

O objetivo deve ser específico o suficiente para delimitar a mudança.

Evite objetivos vagos como:

- "melhorar o sistema";
- "corrigir o código";
- "otimizar a aplicação".

Prefira descrever o comportamento ou resultado concreto desejado.

# Contexto

Registre somente contexto relevante para compreender a especificação.

Quando aplicável, incluir:

- comportamento atual;
- componente afetado;
- motivo da mudança;
- limitação existente;
- decisão anterior relevante;
- dependência conhecida.

Não transformar a seção de contexto em análise arquitetural extensa.

# Escopo incluído

Liste explicitamente o que pertence à mudança solicitada.

Cada item deve representar:

- comportamento a ser alterado;
- capacidade a ser adicionada;
- condição a ser atendida;
- configuração a ser modificada;
- resultado que precisa ser produzido.

Não incluir implementação técnica detalhada.

# Escopo excluído

Registre explicitamente o que não faz parte desta especificação.

Quando aplicável, incluir exclusões como:

- refatoração geral;
- melhorias não solicitadas;
- alterações arquiteturais adicionais;
- mudança em contratos públicos;
- atualização de dependências;
- paginação;
- fallback adicional;
- alterações de infraestrutura;
- correção de bugs não relacionados.

Itens excluídos não devem reaparecer posteriormente como requisitos implícitos.

# Requisitos funcionais

Cada requisito funcional deve descrever comportamento observável.

Quando útil, identificar como:

- RF1
- RF2
- RF3

Exemplo conceitual:

`RF1 — O sistema deve utilizar 150000 como valor default quando a variável de ambiente não estiver definida.`

Cada requisito deve deixar claro:

- condição;
- comportamento esperado;
- resultado observável.

Não descrever implementação interna desnecessariamente.

# Requisitos não funcionais

Registrar somente requisitos não funcionais realmente aplicáveis, como:

- compatibilidade;
- desempenho;
- segurança;
- observabilidade;
- confiabilidade;
- reversibilidade;
- manutenção;
- estabilidade operacional.

Não inventar requisitos não funcionais apenas para preencher a seção.

Quando nenhum requisito específico existir, informar isso explicitamente.

# Restrições

Registrar restrições que limitam a solução futura.

Podem incluir:

- arquivos ou componentes que não podem ser alterados;
- contratos que devem ser preservados;
- comportamento que não pode mudar;
- tecnologias que devem permanecer;
- limites operacionais;
- restrições de produção;
- decisões explicitamente aprovadas pelo usuário.

Restrições devem ser tratadas como limites da especificação, não como sugestões.

# Critérios de aceite

Os critérios de aceite devem ser objetivos e verificáveis.

Quando útil, identificar como:

- CA1
- CA2
- CA3

Cada critério deve permitir determinar claramente se a especificação foi atendida.

Prefira critérios como:

- determinado valor passa a ser utilizado;
- comportamento anterior permanece inalterado;
- determinada entrada produz determinada saída;
- configuração existente continua suportada;
- cenário específico não sofre regressão.

Evite critérios vagos como:

- "funcionar corretamente";
- "não apresentar problemas";
- "estar otimizado".

Os critérios devem validar o resultado, não prescrever a implementação.

# Ambiguidades

Registrar qualquer ponto que ainda permita interpretações diferentes capazes de alterar:

- escopo;
- comportamento;
- requisito;
- compatibilidade;
- risco;
- critério de aceite.

Para cada ambiguidade, quando útil, indicar:

- o que está indefinido;
- por que isso importa;
- qual decisão ainda é necessária.

Não tentar resolver silenciosamente ambiguidade crítica.

## Quando não houver ambiguidades

Se todas as decisões necessárias já estiverem determinadas:

- informar explicitamente que não foram encontradas ambiguidades bloqueantes;
- não criar dúvidas artificiais;
- não inventar perguntas apenas para preencher a seção.

# Separação entre requisito e solução

Durante `/specify`, descreva:

`o que deve acontecer`

e não:

`como o código deverá ser implementado`.

Evite definir prematuramente:

- nomes finais de funções;
- classes;
- algoritmos detalhados;
- estruturas internas;
- sequência exata de chamadas;
- diff por arquivo;
- pseudocódigo de implementação;
- divisão em tarefas.

Quando uma sugestão técnica for importante para registrar contexto, marque explicitamente como:

`Sugestão técnica — não faz parte do requisito aprovado.`

Ela não deve ser transformada automaticamente em requisito.

# Resumo

Ao final, produza um pequeno parágrafo consolidando:

- objetivo;
- mudança esperada;
- principais restrições;
- escopo;
- ambiguidades relevantes.

O resumo não deve introduzir informação nova.

# Próxima etapa recomendada

Determine a próxima etapa com base no estado da especificação.

Se existirem ambiguidades relevantes:

`Próxima etapa recomendada: /clarify`

Se não houver ambiguidades relevantes e a especificação estiver suficientemente definida:

`Próxima etapa recomendada: /planning`

A próxima etapa deve ser apenas recomendada.

Não executá-la automaticamente.

# Saída obrigatória

Responder com:

1. Objetivo.
2. Contexto.
3. Escopo incluído.
4. Escopo excluído.
5. Requisitos funcionais.
6. Requisitos não funcionais.
7. Restrições.
8. Critérios de aceite.
9. Ambiguidades.
10. Pequeno parágrafo com o resumo do resultado e das ambiguidades.
11. Próxima etapa recomendada.

## Regra crítica

Este workflow existe exclusivamente para especificar a solicitação.

Não alterar arquivos.

Não modificar código.

Não planejar implementação detalhada.

Não criar tarefas.

Não implementar.

Não ampliar o escopo.

Não transformar sugestão técnica em requisito sem confirmação.

Não avançar automaticamente para `/clarify`, `/planning` ou qualquer outra etapa.