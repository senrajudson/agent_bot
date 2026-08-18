---
description: Executa exclusivamente a skill validate para revisar uma mudança aplicada, inspecionar diff, executar testes/checks e comparar o resultado com os critérios de aceite, sem corrigir automaticamente.
---

# Validate

Quando este workflow for invocado com `/validate`, execute exclusivamente a skill localizada em:

`.agents/skills/validate/SKILL.md`

## Instruções de execução

1. Leia integralmente `.agents/skills/validate/SKILL.md`.
2. Considere o conteúdo dessa skill como a autoridade para esta execução.
3. Execute somente a etapa de validação definida nessa skill.
4. Utilize como fontes, quando disponíveis:
   - tarefa implementada;
   - plano aprovado;
   - especificação aprovada;
   - critérios de aceite;
   - checklist relacionado;
   - diff atual;
   - testes existentes;
   - documentação relevante;
   - contexto da conversa.
5. Valide somente a mudança que foi implementada.
6. Compare o resultado real com o comportamento esperado.
7. Diferencie claramente:
   - falha real;
   - regressão potencial;
   - risco residual;
   - melhoria opcional;
   - pendência de documentação.
8. Não transformar melhoria opcional em falha.
9. Não corrigir automaticamente qualquer problema encontrado.
10. Produza a resposta conforme as validações esperadas da skill `validate`.

## Restrições

Durante esta execução:

- Não executar outras skills.
- Não executar outros workflows.
- Não iniciar `/analyze`.
- Não iniciar `/specify`.
- Não iniciar `/clarify`.
- Não iniciar `/planning`.
- Não iniciar `/tasks`.
- Não iniciar `/checklist`.
- Não iniciar `/implement`.
- Não modificar arquivos.
- Não criar arquivos.
- Não implementar novas mudanças.
- Não corrigir falhas.
- Não aplicar patches.
- Não refatorar código.
- Não alterar documentação.
- Não alterar testes para fazê-los passar.
- Não ampliar o escopo.
- Não executar comandos destrutivos.
- Não avançar automaticamente para outra etapa.

# Preparação da validação

Antes de executar testes ou checks:

1. Identifique qual mudança está sendo validada.
2. Identifique a tarefa ou escopo aprovado correspondente.
3. Identifique os arquivos que deveriam ter sido alterados.
4. Identifique os arquivos realmente alterados.
5. Identifique os critérios de aceite aplicáveis.
6. Identifique os testes/checks previstos.
7. Determine se existem alterações fora do escopo.

Se não for possível identificar com segurança qual mudança deve ser validada, não invente contexto.

Informe a limitação e solicite ao usuário a tarefa, diff ou escopo correspondente.

# Validação dos arquivos alterados

Verifique:

- quais arquivos foram modificados;
- se todos pertencem ao escopo aprovado;
- se algum arquivo esperado deixou de ser alterado;
- se algum arquivo não autorizado foi modificado;
- se houve criação ou remoção inesperada de arquivos.

Quando houver alteração fora da lista autorizada, registre explicitamente como potencial violação de escopo.

Não reverta nem corrija o arquivo.

# Revisão do diff

Analise o diff da mudança e descreva objetivamente:

- o que foi alterado;
- onde foi alterado;
- qual comportamento mudou;
- qual comportamento foi preservado;
- se existem mudanças não relacionadas.

Procure especialmente por:

- alterações oportunistas;
- refatorações não aprovadas;
- mudança de contrato;
- mudança de configuração não prevista;
- alteração de comportamento não solicitada;
- remoção de fallback;
- alteração de tratamento de erro;
- mudança de valores default;
- impacto em compatibilidade.

Não considere o diff correto apenas porque compila ou passa testes.

# Critérios de aceite

Para cada critério de aceite aplicável:

1. Identifique o critério.
2. Determine como ele foi validado.
3. Informe o resultado.

Classifique cada critério como:

- `ATENDIDO`
- `NÃO ATENDIDO`
- `PARCIALMENTE ATENDIDO`
- `NÃO VALIDADO`

Não declarar um critério como atendido sem evidência suficiente.

Quando um critério não puder ser validado, explicar o motivo.

# Testes e checks

Execute somente testes e checks relacionados à mudança.

Quando aplicável, considere:

- testes unitários;
- testes de integração;
- testes de regressão;
- lint;
- type check;
- validação de configuração;
- build;
- inspeção de diff;
- validação manual.

Não executar ações destrutivas ou irreversíveis.

Não executar testes que dependam de produção real sem autorização explícita.

## Ao executar comandos

Para cada comando executado, registrar:

- comando;
- objetivo;
- resultado;
- código de saída quando disponível.

Não omitir falhas.

Não repetir testes indefinidamente tentando obter sucesso.

# Resultado dos testes

Classifique os testes como:

- `PASSOU`
- `FALHOU`
- `NÃO EXECUTADO`
- `BLOQUEADO`

Quando um teste falhar, determine se a falha é:

- relacionada à mudança;
- provavelmente relacionada;
- provavelmente não relacionada;
- inconclusiva.

Não corrigir a falha.

Não alterar o teste.

Não alterar o código para fazer o teste passar.

# Regressões potenciais

Avalie possíveis impactos em comportamentos existentes diretamente relacionados à mudança.

Priorize:

- contratos existentes;
- caminhos alternativos;
- tratamento de erro;
- configuração;
- compatibilidade;
- valores default;
- integrações;
- desempenho;
- observabilidade.

Diferencie:

`regressão confirmada`

de:

`regressão potencial`

Não declarar regressão sem evidência.

# Riscos restantes

Registre riscos que permaneçam após a validação.

Para cada risco relevante, indicar:

- descrição;
- impacto;
- evidência;
- necessidade de ação.

Não criar riscos genéricos apenas para preencher a seção.

# Documentação afetada

Verifique se a mudança exige atualização documental.

Considere, quando aplicável:

- README;
- documentação técnica;
- configuração;
- exemplos;
- comentários relevantes;
- documentação operacional;
- governança.

Classifique como:

- documentação atualizada;
- documentação não afetada;
- atualização recomendada;
- atualização necessária.

Não alterar documentação durante `/validate`.

# Problemas encontrados

Se encontrar um problema:

1. Descreva o problema.
2. Informe a evidência.
3. Informe o impacto.
4. Classifique a severidade quando possível.
5. Relacione o problema ao critério de aceite ou comportamento afetado.
6. Recomende a próxima ação.

Não corrigir.

Não executar `/implement`.

Não modificar arquivos.

# Melhorias opcionais

Se identificar melhoria que não representa falha da implementação:

registre separadamente como:

`Melhoria opcional`

Não classifique como erro.

Não inclua como condição para aprovação, salvo se já fizer parte dos critérios de aceite.

# Resultado geral da validação

Ao final, classifique a validação como uma destas opções:

- `APROVADA`
- `APROVADA COM RESSALVAS`
- `REPROVADA`
- `INCONCLUSIVA`

## APROVADA

Utilizar quando:

- critérios obrigatórios foram atendidos;
- testes relevantes passaram;
- não existem regressões confirmadas;
- não existem violações relevantes de escopo.

## APROVADA COM RESSALVAS

Utilizar quando:

- critérios obrigatórios foram atendidos;
- não existe falha bloqueante;
- permanecem riscos ou pendências não bloqueantes.

## REPROVADA

Utilizar quando existir, por exemplo:

- critério obrigatório não atendido;
- regressão confirmada;
- teste relevante falhando por causa da mudança;
- comportamento fora do escopo introduzido;
- violação relevante do plano aprovado.

## INCONCLUSIVA

Utilizar quando não houver evidência suficiente para determinar o resultado com segurança.

# Próxima ação recomendada

Se a validação estiver:

`APROVADA`
- informar que nenhuma correção é necessária nesta etapa.

`APROVADA COM RESSALVAS`
- indicar as pendências ou riscos a acompanhar.

`REPROVADA`
- recomendar retorno a `/implement` somente para uma correção explicitamente aprovada.

`INCONCLUSIVA`
- indicar qual evidência, ambiente, teste ou informação falta.

A próxima ação deve ser apenas recomendada.

Não executá-la automaticamente.

# Saída obrigatória

Responder com:

1. Arquivos alterados.
2. Diff resumido.
3. Critérios de aceite.
4. Testes executados.
5. Resultado dos testes.
6. Riscos restantes.
7. Regressões potenciais.
8. Documentação afetada.
9. Próxima ação recomendada.

Adicionar também ao final:

10. Resultado geral da validação:
   - APROVADA;
   - APROVADA COM RESSALVAS;
   - REPROVADA;
   - INCONCLUSIVA.

# Regra crítica

Este workflow existe exclusivamente para validar uma mudança já aplicada.

Se encontrar problema, reportar.

Não corrigir automaticamente.

Não alterar arquivos.

Não implementar novas mudanças.

Não alterar testes para produzir sucesso artificial.

Não ampliar o escopo.

Não avançar automaticamente para `/implement` ou qualquer outra etapa.