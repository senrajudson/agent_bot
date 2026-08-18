---
description: Executa exclusivamente a skill constitution para criar, revisar ou atualizar documentos Markdown de governança do projeto, exigindo confirmação explícita antes de qualquer edição.
---

# Constitution

Quando este workflow for invocado com `/constitution`, execute exclusivamente a skill localizada em:

`.agents/skills/constitution/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/constitution/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a etapa de governança definida nessa skill.
4. Use como contexto:
   - solicitação atual do usuário;
   - código existente;
   - documentação existente;
   - decisões aprovadas anteriormente;
   - regras já presentes no documento de governança.
5. Não trate arquitetura desejada, proposta ou futura como estado atual.
6. Não transforme recomendação em regra obrigatória sem aprovação explícita.
7. Diferencie claramente:
   - regra obrigatória;
   - recomendação;
   - dívida técnica;
   - decisão pendente;
   - prática futura.
8. Preserve regras existentes que não estejam diretamente relacionadas à alteração solicitada.
9. Limite qualquer edição estritamente ao documento e às seções aprovadas pelo usuário.

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
- Não iniciar `/implement`.
- Não iniciar `/validate`.
- Não alterar código de aplicação.
- Não alterar comportamento funcional.
- Não alterar prompts de LLM do produto.
- Não alterar integrações.
- Não criar implementação.
- Não criar tarefas.
- Não executar testes de implementação.
- Não editar nenhum documento antes de confirmação explícita.
- Não alterar arquivos fora do escopo aprovado.
- Não avançar automaticamente para outra etapa.

# Fase 1 — Proposta de atualização

Antes de modificar qualquer arquivo, determine:

1. Qual é o documento alvo.
2. Por que a atualização é necessária.
3. Quais seções precisam ser alteradas.
4. Qual é o tipo de mudança:
   - nova regra;
   - correção de inconsistência;
   - reorganização;
   - remoção de regra obsoleta;
   - esclarecimento de regra existente.
5. Se a mudança proposta está sustentada por:
   - código real;
   - documentação existente;
   - decisão explícita do usuário;
   - regra já aprovada.

## Validação contra o estado real

Antes de propor uma alteração de governança, consulte quando necessário:

- código relevante;
- estrutura atual do projeto;
- configuração existente;
- documentação;
- workflows;
- skills;
- testes;
- decisões anteriores disponíveis no contexto.

Não assuma que o documento atual está correto apenas por estar documentado.

Se houver divergência entre documentação e implementação, registre explicitamente a inconsistência.

Não corrija código para adequá-lo à documentação durante esta etapa.

## Saída obrigatória antes da edição

Antes de editar, responda com:

1. Documento alvo.
2. Motivo da atualização.
3. Seções afetadas.
4. Resumo da mudança proposta.
5. Riscos da mudança.
6. Confirmação necessária antes de editar.

## Gate de confirmação

Após apresentar a proposta:

- Pare a execução.
- Aguarde confirmação explícita do usuário.
- Não edite nenhum arquivo enquanto a confirmação não existir.

São exemplos de confirmação explícita:

- "pode aplicar";
- "aprovado";
- "pode atualizar";
- "faça a alteração";
- confirmação equivalente e inequívoca.

Não considere silêncio, ausência de objeção ou mensagem ambígua como aprovação.

# Fase 2 — Atualização aprovada

Somente após confirmação explícita:

1. Releia a solicitação aprovada.
2. Confirme qual documento foi autorizado.
3. Confirme quais seções foram autorizadas.
4. Edite somente o arquivo Markdown aprovado.
5. Altere somente as seções necessárias.
6. Preserve conteúdo não relacionado.
7. Não amplie o escopo durante a edição.
8. Não introduza novas regras que não estavam incluídas na proposta aprovada.
9. Não altere código ou outros arquivos do projeto.

## Regras de governança obrigatórias

Quando forem aplicáveis ao documento alvo, preservar ou registrar corretamente as seguintes regras:

- `/tasks` nunca executa tarefas.
- `/plan` nunca altera código.
- `/specify` nunca propõe implementação detalhada.
- `/implement` só executa tarefa aprovada.
- `/validate` não corrige automaticamente.
- mudanças devem ser pequenas, revisáveis e reversíveis.
- código fora do escopo não deve ser alterado.
- documentação deve refletir o código real.
- arquitetura ideal deve ser identificada como plano ou estado futuro, nunca como implementação atual.

Não adicionar essas regras novamente se já estiverem presentes de forma equivalente.

## Controle de escopo

Durante a edição:

- Não reorganizar outras partes do documento por conveniência.
- Não reescrever seções não relacionadas.
- Não aplicar melhorias editoriais fora do escopo aprovado.
- Não modificar formatação global sem necessidade.
- Não remover regras existentes sem autorização.
- Não alterar outro documento de governança automaticamente.

Se durante a edição surgir necessidade de uma mudança adicional, registre-a como pendência.

Não execute essa mudança adicional sem nova aprovação.

# Finalização

Após concluir uma atualização aprovada, responda com:

1. Arquivo Markdown alterado.
2. Seções modificadas.
3. Regras adicionadas.
4. Regras removidas.
5. Inconsistências corrigidas.
6. Pendências ou decisões futuras.

Se nenhuma regra tiver sido adicionada ou removida, informe explicitamente:

- Regras adicionadas: nenhuma.
- Regras removidas: nenhuma.

## Regra crítica

Este workflow possui dois gates distintos:

Fase 1:
propor a alteração e aguardar aprovação.

Fase 2:
editar somente após confirmação explícita.

Nunca editar antes da confirmação.

Nunca alterar código de aplicação.

Nunca ampliar o escopo aprovado.

Nunca avançar automaticamente para outra etapa.