---
description: Executa exclusivamente a skill tasks para decompor um plano aprovado em tarefas pequenas, sequenciais, verificáveis e reversíveis, sem executar nenhuma delas.
---

# Tasks

Quando este workflow for invocado com `/tasks`, execute exclusivamente a skill localizada em:

`.agents/skills/tasks/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/tasks/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a etapa de decomposição em tarefas definida nessa skill.
4. Utilize como fonte principal um plano técnico previamente aprovado.
5. Considere também, quando disponíveis:
   - especificação aprovada;
   - decisões consolidadas em `/clarify`;
   - critérios de aceite;
   - restrições de governança;
   - contexto atual da conversa.
6. Transforme o plano aprovado em tarefas pequenas, sequenciais e verificáveis.
7. Cada tarefa deve representar uma unidade de mudança que possa ser revisada e validada isoladamente.
8. Preserve rigorosamente o escopo definido pelo plano.
9. Não introduza trabalho que não esteja sustentado pelo plano aprovado.
10. Produza cada tarefa conforme a seção "Saída obrigatória" da skill `tasks`.

## Restrições

Durante esta execução:

- Não executar outras skills.
- Não executar outros workflows.
- Não iniciar `/analyze`.
- Não iniciar `/specify`.
- Não iniciar `/clarify`.
- Não iniciar `/planning`.
- Não iniciar `/plan`.
- Não iniciar `/checklist`.
- Não iniciar `/implement`.
- Não iniciar `/validate`.
- Não alterar arquivos.
- Não criar arquivos.
- Não modificar código.
- Não implementar tarefas.
- Não executar comandos.
- Não executar testes.
- Não executar checks.
- Não corrigir código.
- Não aplicar mudanças.
- Não realizar refatorações.
- Não ampliar o escopo.
- Não executar nenhuma tarefa gerada.
- Não avançar automaticamente para `/implement` ou qualquer outra etapa.

# Pré-condição — Plano aprovado

Antes de gerar qualquer tarefa:

1. Identifique qual plano será utilizado.
2. Confirme que o plano representa o escopo atualmente aprovado.
3. Identifique:
   - objetivo técnico;
   - estratégia;
   - arquivos impactados;
   - escopo excluído;
   - critérios de aceite;
   - testes/checks previstos;
   - ordem recomendada.
4. Confirme que existem informações suficientes para decompor o plano com segurança.

## Se não houver plano aprovado

Se não for possível identificar um plano aprovado:

1. Não invente um plano.
2. Não inferir uma estratégia de implementação completa.
3. Não gerar tarefas especulativas.
4. Informe que `/tasks` requer um plano aprovado como entrada.
5. Solicite que o usuário forneça ou execute a etapa de planejamento apropriada.

Encerre o workflow nesse ponto.

# Fonte de verdade

Utilize a seguinte prioridade:

1. Plano explicitamente aprovado.
2. Decisões explícitas do usuário posteriores ao plano.
3. Especificação aprovada.
4. Decisões consolidadas em `/clarify`.
5. Restrições de governança aplicáveis.
6. Código ou documentação apenas quando necessários para interpretar corretamente o plano.

Se uma decisão posterior do usuário alterar o plano, considere apenas a parte explicitamente modificada.

Não reinterpretar silenciosamente o restante do plano.

# Granularidade das tarefas

Cada tarefa deve ser:

- pequena;
- objetiva;
- revisável;
- reversível;
- verificável;
- limitada a um único objetivo técnico coerente.

Não agrupar em uma única tarefa mudanças independentes apenas porque pertencem à mesma feature.

Evite tarefas como:

`T001 — Implementar toda a funcionalidade`

Prefira decomposição como:

`T001 — Ajustar configuração necessária`

`T002 — Atualizar consumidor da configuração`

`T003 — Atualizar testes relacionados`

quando essa separação estiver sustentada pelo plano.

## Não fragmentar excessivamente

Também não divida uma alteração atômica em tarefas artificiais.

Uma tarefa deve representar a menor unidade que faça sentido técnico e possa ser revisada isoladamente.

# Sequenciamento

Organize as tarefas na ordem necessária para execução.

Quando uma tarefa depender de outra, registre explicitamente a dependência.

Exemplo:

`Depende de: T001`

Se não houver dependência:

`Depende de: nenhuma`

Não gerar tarefas paralelas como sequenciais sem necessidade.

# IDs

Utilize IDs sequenciais e estáveis:

- T001
- T002
- T003
- T004

Não reutilize o mesmo ID para tarefas diferentes dentro da mesma lista.

# Arquivos permitidos

Para cada tarefa, liste somente os arquivos que poderão ser alterados durante sua futura implementação.

Os arquivos permitidos devem estar sustentados pelo plano aprovado.

Se um arquivo ainda não puder ser determinado com segurança, não invente um caminho.

Registre:

`pendente de confirmação`

quando necessário.

A lista de arquivos permitidos funciona como limite de escopo para futura execução de `/implement`.

# Arquivos proibidos

Para cada tarefa, identifique arquivos ou grupos de arquivos que não devem ser modificados naquela tarefa quando isso ajudar a proteger o escopo.

Priorize arquivos:

- próximos ao componente alterado;
- potencialmente afetados por refatorações oportunistas;
- explicitamente excluídos pelo plano;
- contendo contratos que devem permanecer intactos;
- relacionados a infraestrutura fora do escopo.

Quando não houver arquivos específicos, registrar:

`Todos os arquivos não listados em "Arquivos permitidos".`

Isso deve ser considerado o comportamento padrão.

# Passos

Os passos devem descrever o trabalho necessário para completar a tarefa.

Eles devem indicar:

- o que deve ser alterado;
- onde;
- qual comportamento deve ser preservado;
- qual resultado deve ser alcançado.

Os passos não devem:

- conter implementação completa;
- escrever código final;
- antecipar diffs completos;
- executar comandos;
- executar testes;
- incluir trabalho pertencente a outra tarefa.

O objetivo é tornar a tarefa executável posteriormente pelo `/implement`, não executá-la agora.

# Critério de aceite

Cada tarefa deve possuir critérios objetivos de conclusão.

O critério deve permitir responder claramente:

`esta tarefa foi concluída: sim ou não`

Evite:

- "funcionar corretamente";
- "ficar melhor";
- "não apresentar problema".

Prefira condições observáveis e verificáveis.

O critério da tarefa deve estar alinhado aos critérios de aceite do plano e da especificação.

# Testes/checks

Liste apenas testes ou checks que deverão ser executados posteriormente para validar aquela tarefa.

Pode incluir, quando aplicável:

- teste unitário;
- teste de integração;
- teste de regressão;
- lint;
- type check;
- validação de configuração;
- inspeção de diff;
- teste manual específico.

Não execute nenhum deles durante `/tasks`.

Se nenhum teste automatizado for aplicável, registre o check manual necessário.

# Risco

Classifique o risco da tarefa como:

- baixo;
- médio;
- alto.

Explique brevemente o motivo.

Considere fatores como:

- impacto funcional;
- regressão;
- compatibilidade;
- dados;
- contratos;
- infraestrutura;
- configuração;
- produção;
- número de componentes afetados.

Não classificar automaticamente todas as tarefas como baixo risco.

# Escopo excluído

Itens explicitamente fora do plano não devem virar tarefas.

Não criar tarefas para:

- refatorações opcionais;
- limpeza de código;
- melhorias de estilo;
- bugs não relacionados;
- documentação não prevista;
- alterações arquiteturais adicionais;
- atualização de dependências não necessária;
- infraestrutura fora do escopo;
- otimizações não aprovadas.

Se identificar algo relevante fora do escopo, registre separadamente como:

`Observação fora do escopo`

Não criar uma tarefa para isso.

# Formato obrigatório de cada tarefa

Utilize a seguinte estrutura:

## T001 — Nome da tarefa

**Objetivo**

Descrição objetiva do resultado desta tarefa.

**Arquivos permitidos**

- `caminho/do/arquivo`

**Arquivos proibidos**

- Todos os arquivos não listados em "Arquivos permitidos".

**Passos**

1. Passo necessário.
2. Passo necessário.
3. Passo necessário.

**Critério de aceite**

- Condição objetiva e verificável.

**Testes/checks**

- Teste ou check que deverá ser executado posteriormente.

**Risco**

- Nível: baixo/médio/alto
- Motivo: descrição objetiva.

**Depende de**

- Tarefa anterior ou `nenhuma`.

# Verificação final da lista

Antes de apresentar o resultado, confirme:

1. Todas as tarefas pertencem ao plano aprovado.
2. Nenhuma tarefa executa trabalho fora do escopo.
3. Cada tarefa possui apenas um objetivo técnico coerente.
4. Cada tarefa possui arquivos permitidos claramente delimitados.
5. Cada tarefa possui critério de aceite verificável.
6. Cada tarefa possui testes/checks definidos.
7. As dependências estão coerentes.
8. A ordem permite implementação incremental.
9. Nenhuma tarefa foi executada.
10. Nenhum arquivo foi alterado.

# Saída obrigatória

Para cada tarefa, responder com:

1. ID.
2. Nome.
3. Objetivo.
4. Arquivos permitidos.
5. Arquivos proibidos.
6. Passos.
7. Critério de aceite.
8. Testes/checks.
9. Risco.

Quando houver dependências entre tarefas, informar também:

10. Depende de.

# Regra crítica

Este workflow existe exclusivamente para transformar um plano aprovado em uma lista de tarefas.

`/tasks` nunca executa tarefas.

Não alterar arquivos.

Não criar arquivos.

Não modificar código.

Não executar comandos.

Não executar testes.

Não implementar.

Não corrigir problemas encontrados.

Não criar trabalho fora do plano aprovado.

Não avançar automaticamente para `/implement` ou qualquer outra etapa.

A execução termina quando a lista de tarefas estiver completamente definida.