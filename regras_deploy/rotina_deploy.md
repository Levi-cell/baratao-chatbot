# Rotina operacional da VM do Baratão

A instalação usa o checkout em `/opt/chatbot/app`, o ambiente Python em `/opt/chatbot/venv` e o arquivo de configuração em `/etc/chatbot/chatbot.env`. O registro da última entrega está em [VERSIONAMENTO.md](../VERSIONAMENTO.md).

## Antes de atualizar

Verificar a revisão, se a árvore da VM está limpa, os commits recebidos por `git fetch origin` e a diferença de arquivos. Registrar quais das [três unidades systemd](../deploy/systemd) estão ativas e habilitadas. Identificar migrations incrementais e compatibilidade dos processos envolvidos. Para mudança de schema, confirmar backup e possibilidade de restauração antes de interromper o atendimento.

## Ordem da manutenção

1. Para mudar o schema compartilhado, pausar o webhook, o flow e o consumo Meta. Para uma alteração isolada do painel, conferir se basta atualizar estáticos e recarregar o Gunicorn.
2. Com a árvore limpa, conferir a branch e o upstream configurados e aplicar o avanço com `git pull --ff-only`. Conferir o SHA resultante. Após atualizar unidades systemd, executar `systemctl daemon-reload`.
3. Aplicar a migração específica da versão ao banco existente. Executar verificações com o usuário `chatbot`, o Python do venv e o mesmo ambiente do serviço. Usar `callback/manage.py check`, testes unitários pertinentes e `collectstatic --noinput` quando houver arquivos estáticos. Os testes que criam ou alteram estrutura usam banco de testes isolado.
4. Restabelecer os serviços que estavam ativos. Conferir `chatbot-webhook.service`, `chatbot-worker-flow.service` e `chatbot-worker-consumo-meta.service` pelos campos `ActiveState`, `SubState` e `NRestarts`, pelos logs e pela resposta dos endpoints.
5. Conferir os ciclos nos logs e uma leitura autenticada do painel. Um ciclo com zero selecionados pode ser normal.

## Se uma etapa falhar

Guardar o SHA, o erro e a saída das validações. Identificar se o schema ou algum envio externo já mudou. A reversão de código depende de compatibilidade com o banco e as filas daquela instalação. O [guia de implantação](../deploy/README.md) cobre setup inicial, TLS, estáticos, migrações e configuração do worker de consumo Meta.
