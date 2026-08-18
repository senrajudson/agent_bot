---
description: Executa exclusivamente a skill planning para criar um plano técnico incremental, seguro e restrito ao escopo, sem alterar arquivos ou implementar.
---

# Planning

Quando este workflow for invocado com `/planning`, execute exclusivamente a skill localizada em:

`.agents/skills/planning/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/planning/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a etapa de planejamento técnico definida nessa skill.
4. Utilize como base, quando disponíveis:
   - análise anterior;
   - especificação aprovada;
   - decisões consolidadas em `/clarify`;
   - documentação relevante;
   - código existente;
   - restrições de governança do projeto.
5. Planeje somente o escopo solicitado.
6. Preserve o comportamento atual salvo quando houver autorização explícita para alterá-lo.
7. Prefira mudanças pequenas, incrementais, revisáveis e reversíveis.
8. Não introduza melhorias ou refatorações não necessárias para cumprir o objetivo.
9. Produza a resposta conforme a seção "Saída obrigatória" da skill `planning`.

## Restrições

Durante esta execução:

- Não executar outras skills.
- Não executar outros workflows.
- Não iniciar `/analyze`.
- Não iniciar `/specify`.
- Não iniciar `/clarify`.
- Não iniciar `/tasks`.
- Não iniciar `/checklist`.
- Não iniciar `/implement`.
- Não iniciar `/validate`.
- Não alterar arquivos.
- Não criar arquivos de implementação.
- Não executar implementação.
- Não aplicar correções.
- Não criar tarefas detalhadas.
- Não executar comandos destrutivos.
- Não realizar refatoração oportunista.
- Não modificar código fora do escopo.
- Não alterar contratos públicos sem necessidade explicitamente aprovada.
- Não alterar prompts, integrações, Docker ou infraestrutura se isso não fizer parte do escopo aprovado.
- Não avançar automaticamente para outra etapa.

## Preparação do plano

Antes de propor a estratégia:

1. Identifique o objetivo técnico da mudança.
2. Determine o comportamento atual relevante.
3. Identifique as restrições já aprovadas.
4. Identifique os arquivos ou componentes provavelmente impactados.
5. Identifique explicitamente o que está fora do escopo.
6. Avalie os principais riscos técnicos e operacionais.
7. Defina critérios objetivos de aceite.
8. Determine os testes e checks necessários para validar posteriormente a implementação.

## Estratégia proposta

A estratégia deve:

- ser incremental;
- minimizar superfície de alteração;
- preservar contratos e comportamento não relacionados;
- evitar mudanças arquiteturais desnecessárias;
- considerar dependências reais;
- indicar onde a mudança deve ocorrer;
- explicar por que aquela abordagem é adequada.

Quando existirem múltiplas estratégias possíveis, escolha uma estratégia recomendada e registre alternativas somente se elas forem tecnicamente relevantes.

Não criar uma exploração extensa de alternativas quando já existir uma solução claramente preferível.

## Arquivos provavelmente impactados

Liste somente arquivos que tenham relação concreta ou provável com a mudança.

Para cada arquivo, informe:

- caminho;
- responsabilidade atual relevante;
- alteração prevista;
- motivo da alteração.

Se um arquivo ainda não puder ser confirmado, marque-o explicitamente como:

`provável, pendente de confirmação`

Não declare arquivo como impactado apenas por proximidade arquitetural.

## Alteração prevista por arquivo

Descreva o tipo de alteração esperada sem escrever a implementação final.

É permitido indicar, por exemplo:

- ajuste de valor default;
- inclusão de validação;
- alteração de chamada existente;
- extensão de configuração;
- atualização de teste;
- atualização de documentação.

Evite fornecer código final completo nesta etapa.

O plano deve explicar `o que` será alterado e `onde`, sem transformar a etapa em implementação antecipada.

## Escopo excluído

Registre explicitamente tudo que foi considerado, mas não faz parte da mudança.

Quando aplicável, incluir itens como:

- refatoração geral;
- melhorias de estilo;
- paginação;
- fallback adicional;
- alterações arquiteturais;
- novas abstrações;
- mudanças em contratos públicos;
- alterações de infraestrutura;
- atualização de dependências;
- correção de bugs não relacionados.

Itens fora do escopo não devem reaparecer posteriormente como parte implícita da implementação.

## Riscos

Para cada risco relevante, descreva:

- risco;
- causa;
- impacto provável;
- probabilidade quando possível determinar qualitativamente.

Priorize riscos relacionados a:

- regressão;
- compatibilidade;
- comportamento funcional;
- produção;
- dados;
- contratos;
- performance;
- integração;
- configuração;
- observabilidade.

Não criar riscos genéricos apenas para preencher a seção.

## Mitigações

Cada mitigação deve estar ligada a um risco identificado.

As mitigações podem incluir:

- alteração mínima;
- preservação de fallback existente;
- teste específico;
- validação de configuração;
- comparação de comportamento antes/depois;
- rollback simples;
- isolamento de mudança.

Não transformar mitigação em nova funcionalidade fora do escopo.

## Critérios de aceite

Os critérios devem ser verificáveis.

Prefira critérios como:

- valor esperado configurado corretamente;
- comportamento específico preservado;
- determinado teste passando;
- ausência de alteração em contrato;
- configuração via ENV continuando funcional.

Evite critérios vagos como:

- "funcionar corretamente";
- "estar melhor";
- "não ter problemas".

Cada critério deve permitir posteriormente determinar objetivamente se a implementação foi aceita ou rejeitada.

## Testes e checks necessários

Defina somente testes e checks relevantes à mudança.

Quando aplicável, separar em:

- teste unitário;
- teste de integração;
- teste de regressão;
- lint;
- type check;
- validação de configuração;
- inspeção de diff;
- validação manual.

Não executar esses testes nesta etapa.

Apenas definir o que deverá ser validado posteriormente.

## Ordem recomendada

A ordem recomendada deve representar a sequência técnica de implementação, sem decompor ainda em tarefas executáveis detalhadas.

Exemplo conceitual:

1. Ajustar configuração.
2. Atualizar consumidor direto da configuração, se necessário.
3. Atualizar testes relacionados.
4. Validar comportamento.
5. Atualizar documentação relacionada.

Não produzir IDs de tarefas, subtarefas ou backlog nesta etapa.

Isso pertence a `/tasks`.

# Saída obrigatória

Responder com:

1. Objetivo técnico.
2. Estratégia proposta.
3. Arquivos provavelmente impactados.
4. Alteração prevista por arquivo.
5. Escopo excluído.
6. Riscos.
7. Mitigações.
8. Critérios de aceite.
9. Testes/checks necessários.
10. Pequeno parágrafo com o resumo do resultado.
11. Ordem recomendada.

## Regra crítica

Este workflow apenas cria o plano técnico.

Não alterar arquivos.

Não implementar.

Não criar tarefas detalhadas.

Não executar testes.

Não aplicar correções.

Não avançar automaticamente para `/tasks`, `/implement` ou qualquer outra etapa.