---
description: Executa exclusivamente a skill result para registrar no arquivo last_answer a solicitação ou resposta desejada pelo usuário, priorizando o último resultado quando nenhum alvo for especificado.
---

# Result

Quando este workflow for invocado com `/result`, execute exclusivamente a skill localizada em:

`.agents/skills/result/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/result/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a etapa de registro de resultado definida nessa skill.
4. Identifique qual solicitação ou resposta o usuário deseja registrar.
5. Se o usuário indicar explicitamente uma resposta, solicitação ou etapa anterior, utilize exatamente esse conteúdo como alvo.
6. Se o usuário não indicar um alvo específico, utilize prioritariamente a última resposta relevante imediatamente anterior à invocação de `/result`.
7. Não considere o próprio comando `/result` como conteúdo a ser registrado.
8. Preserve o conteúdo original da resposta ou solicitação selecionada.
9. Adicione ao final um pequeno resumo da sessão atual e do contexto em que aquele conteúdo foi produzido.
10. Grave o resultado exclusivamente no arquivo:

`<raiz-do-projeto>/last_answer`

## Restrições

Durante esta execução:

- Não executar outras skills.
- Não executar outros workflows.
- Não iniciar `/analyze`.
- Não iniciar `/specify`.
- Não iniciar `/clarify`.
- Não iniciar `/planning`.
- Não iniciar `/plan`.
- Não iniciar `/tasks`.
- Não iniciar `/checklist`.
- Não iniciar `/implement`.
- Não iniciar `/validate`.
- Não implementar código.
- Não alterar código de aplicação.
- Não modificar configuração.
- Não alterar documentação.
- Não executar tarefas.
- Não aplicar correções.
- Não modificar nenhum arquivo além de `last_answer`.
- Não criar arquivos adicionais.
- Não avançar automaticamente para outra etapa.

# Determinação do conteúdo

Antes de escrever o arquivo, determine o conteúdo alvo utilizando a seguinte prioridade.

## Prioridade 1 — Conteúdo explicitamente solicitado

Se o usuário indicar claramente qual conteúdo deseja registrar, utilize esse conteúdo.

Exemplos:

- `/result salve a resposta do planning`
- `/result registre a especificação anterior`
- `/result salve minha última solicitação`
- `/result salve a resposta sobre o erro do MCP`
- `/result use a resposta anterior ao clarify`

Nesse caso, não substituir o alvo escolhido pela última resposta apenas por ela ser mais recente.

## Prioridade 2 — Última resposta relevante

Se nenhum conteúdo específico for indicado, registre a última resposta útil produzida antes da invocação de `/result`.

Não considerar como alvo:

- o próprio comando `/result`;
- mensagens de confirmação sem conteúdo técnico relevante;
- mensagens intermediárias que não representem o resultado desejado.

Quando houver uma resposta imediatamente anterior claramente associada ao trabalho atual, ela deve ser priorizada.

## Prioridade 3 — Última solicitação relevante

Se não houver uma resposta anterior utilizável, registre a última solicitação relevante do usuário anterior ao comando `/result`.

# Preservação do conteúdo

O conteúdo selecionado deve ser preservado com fidelidade.

Não:

- reescrever;
- melhorar;
- corrigir;
- resumir o conteúdo principal;
- alterar decisões;
- adicionar requisitos;
- remover detalhes técnicos;
- transformar hipóteses em fatos.

O resumo da sessão deve ser adicionado separadamente ao final.

# Arquivo alvo

O único arquivo que este workflow pode criar ou modificar é:

`<raiz-do-projeto>/last_answer`

## Se o arquivo não existir

Crie:

`last_answer`

na raiz do projeto.

Não criar:

- `last_answer.md`;
- `last-answer`;
- `last_answer.txt`;
- diretórios adicionais;

a menos que o usuário solicite explicitamente outro nome.

## Se o arquivo já existir

Substitua seu conteúdo pelo novo resultado selecionado.

O arquivo representa o resultado atualmente escolhido pelo usuário, e não um histórico acumulativo da sessão.

Não fazer append automático de resultados anteriores.

# Estrutura do arquivo

O arquivo `last_answer` deve utilizar a seguinte estrutura:

## Conteúdo

Registrar integralmente a resposta ou solicitação selecionada.

## Resumo da sessão

Adicionar um pequeno resumo contendo:

- contexto da sessão atual;
- objetivo relacionado ao conteúdo registrado;
- etapa do workflow em que o resultado foi produzido;
- decisões relevantes diretamente relacionadas;
- próxima etapa, somente quando ela já estiver indicada pelo contexto.

O resumo deve ser curto e contextual.

Não criar novas decisões ou recomendações que não existiam na conversa.

# Validação antes da escrita

Antes de gravar:

1. Confirme internamente qual conteúdo foi selecionado.
2. Confirme que ele ocorreu antes da invocação atual de `/result`.
3. Confirme que `last_answer` é o único arquivo que será alterado.
4. Confirme que o conteúdo principal não foi reescrito.
5. Confirme que o resumo está separado do conteúdo original.

Após essas verificações, escreva o arquivo.

# Saída obrigatória

Após concluir, responder com:

1. A resposta ou solicitação desejada pelo usuário, normalmente a última.
2. Um pequeno resumo da sessão atual e do contexto da resposta acima.

Também informe que o conteúdo foi registrado em:

`last_answer`

Não declarar que o arquivo foi salvo se a escrita não tiver sido realizada com sucesso.

# Tratamento de erro

Se não for possível identificar uma resposta ou solicitação anterior adequada:

1. Não invente conteúdo.
2. Não sobrescreva `last_answer`.
3. Informe que não foi possível determinar com segurança qual conteúdo deve ser registrado.
4. Solicite que o usuário indique explicitamente o conteúdo desejado.

Se ocorrer erro ao escrever `last_answer`:

1. Não alterar nenhum outro arquivo.
2. Informar o erro.
3. Não tentar contornar o problema modificando outros arquivos ou permissões.
4. Não executar ações destrutivas.

# Regra crítica

Este workflow existe exclusivamente para registrar uma solicitação ou resposta anterior no arquivo `last_answer`.

Se o usuário não especificar qual conteúdo deseja, utilizar a última resposta relevante anterior ao comando `/result`.

Nunca registrar o próprio `/result` como resultado.

Nunca alterar arquivos além de `last_answer`.

Nunca implementar.

Nunca executar tarefas.

Nunca avançar automaticamente para outra etapa.