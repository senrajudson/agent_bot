---
description: Executa exclusivamente a skill implement para implementar uma única tarefa previamente aprovada, com escopo mínimo e confirmação explícita antes de alterar arquivos.
---

# Implement

Quando este workflow for invocado com `/implement`, execute exclusivamente a skill localizada em:

`.agents/skills/implement/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/implement/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a tarefa explicitamente aprovada pelo usuário.
4. Utilize como fonte de verdade:
   - a tarefa aprovada;
   - o plano aprovado, quando existir;
   - a especificação aprovada, quando existir;
   - decisões confirmadas durante `/clarify`;
   - restrições de governança aplicáveis.
5. Não execute nenhuma tarefa além da tarefa atual.
6. Não amplie o escopo por conveniência técnica.
7. Preserve todo comportamento não relacionado à tarefa.
8. Faça a menor alteração necessária para cumprir exatamente o que foi aprovado.

## Restrições

Durante esta execução:

- Não executar outras skills.
- Não executar outros workflows.
- Não iniciar `/analyze`.
- Não iniciar `/specify`.
- Não iniciar `/clarify`.
- Não iniciar `/plan`.
- Não iniciar `/planning`.
- Não iniciar `/tasks`.
- Não iniciar `/checklist`.
- Não iniciar `/validate`.
- Não executar tarefas futuras.
- Não realizar limpeza geral.
- Não refatorar código não relacionado.
- Não alterar comportamento fora do definido.
- Não alterar contratos públicos sem autorização.
- Não alterar prompts de LLM sem autorização.
- Não alterar integrações sem autorização.
- Não alterar Docker sem autorização.
- Não alterar infraestrutura sem autorização.
- Não alterar arquivos fora da lista aprovada.
- Não criar melhorias oportunistas.
- Não avançar automaticamente para outra etapa.

# Fase 1 — Preparação da implementação

Antes de alterar qualquer arquivo:

1. Identifique exatamente qual tarefa será executada.
2. Confirme que a tarefa foi previamente aprovada.
3. Determine os arquivos que precisam ser alterados.
4. Confirme que todos os arquivos estão dentro do escopo permitido.
5. Determine a mudança mínima necessária.
6. Avalie o risco da alteração.
7. Identifique qualquer dependência ou bloqueio relevante.

## Saída obrigatória antes da alteração

Responder com:

1. Tarefa que será executada.
2. Arquivos que serão alterados.
3. Mudança exata prevista.
4. Risco.
5. Confirmação necessária.

## Gate de confirmação

Após apresentar a preparação:

- Pare a execução.
- Aguarde confirmação explícita do usuário.
- Não altere nenhum arquivo antes dessa confirmação.

São exemplos de confirmação explícita:

- "pode implementar";
- "aprovado";
- "pode executar";
- "faça a alteração";
- confirmação equivalente e inequívoca.

Não considerar silêncio, ausência de objeção ou mensagem ambígua como aprovação.

# Fase 2 — Implementação aprovada

Somente após confirmação explícita:

1. Releia a tarefa aprovada.
2. Confirme novamente os arquivos autorizados.
3. Implemente somente a mudança prevista.
4. Altere somente os arquivos necessários.
5. Preserve código e comportamento não relacionados.
6. Não execute tarefas futuras.
7. Não faça refatorações adicionais.
8. Não aproveite a alteração para corrigir outros problemas.
9. Não introduza mudanças arquiteturais não aprovadas.
10. Não altere contratos externos ou públicos sem autorização.

## Controle estrito de escopo

Se durante a implementação surgir necessidade de alterar um arquivo não previsto:

1. Pare a implementação antes de alterar esse arquivo.
2. Explique por que a alteração adicional parece necessária.
3. Informe o impacto no escopo.
4. Solicite confirmação explícita do usuário.

Não considere a aprovação original como autorização automática para ampliar a lista de arquivos.

## Problemas encontrados fora do escopo

Se encontrar:

- bug não relacionado;
- dívida técnica;
- inconsistência arquitetural;
- problema de documentação;
- melhoria possível;
- refatoração desejável;
- falha em componente não pertencente à tarefa;

não corrija.

Registre o achado como pendência e continue apenas se ele não impedir a tarefa aprovada.

Se o problema impedir a implementação segura da tarefa:

1. Pare.
2. Explique o bloqueio.
3. Informe o impacto.
4. Solicite orientação do usuário.

## Alterações proibidas sem autorização específica

Não alterar:

- prompts de LLM;
- integrações externas;
- contratos públicos;
- APIs públicas;
- Dockerfile;
- docker-compose;
- pipelines;
- infraestrutura;
- configuração de produção;
- dependências;
- schemas persistidos;
- migrações;

a menos que estejam explicitamente incluídos na tarefa aprovada.

## Testes e checks

Após implementar:

1. Execute apenas testes e checks diretamente relacionados à mudança.
2. Prefira validações de menor escopo antes de validações mais amplas.
3. Não modifique código adicional apenas para fazer um teste passar sem antes determinar se a falha pertence ao escopo.
4. Se um teste falhar por motivo aparentemente não relacionado:
   - registre a falha;
   - não corrija automaticamente;
   - informe como pendência.
5. Não executar ações destrutivas ou irreversíveis para validar a implementação.

Os testes executados nesta etapa servem apenas para verificar a implementação realizada.

A etapa `/validate`, quando aplicável, continua sendo uma etapa separada.

# Finalização

Ao concluir a implementação, responder com:

1. Arquivos alterados.
2. Resumo do diff.
3. O que foi preservado.
4. Testes/checks executados.
5. Pendências.

## Arquivos alterados

Liste somente arquivos efetivamente modificados.

## Resumo do diff

Descreva objetivamente:

- o que mudou;
- onde mudou;
- qual comportamento foi implementado.

Não apresentar alterações que não foram realizadas.

## O que foi preservado

Informe explicitamente os principais comportamentos, contratos ou arquivos relacionados que permaneceram inalterados.

## Testes/checks executados

Informe:

- comando ou check executado;
- resultado;
- limitações da validação, quando existirem.

Não declarar sucesso de teste que não tenha sido executado.

## Pendências

Registre:

- problemas fora do escopo;
- validações ainda necessárias;
- decisões futuras;
- tarefas relacionadas não executadas.

Não executar essas pendências automaticamente.

## Regra crítica

Este workflow possui dois gates:

Fase 1:
declarar exatamente o que será alterado e aguardar aprovação.

Fase 2:
implementar somente a tarefa e os arquivos aprovados.

Nunca alterar arquivos antes da confirmação explícita.

Nunca executar mais de uma tarefa.

Nunca ampliar o escopo sem nova autorização.

Nunca realizar alterações oportunistas.

Nunca avançar automaticamente para `/validate` ou qualquer outra etapa.
