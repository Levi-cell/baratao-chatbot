# Comparação de clientes bloqueados

O comando consulta os bloqueios na Meta e compara com `chatbot.cliente_bloqueado_meta` em uma transação PostgreSQL de leitura. Cada comparação usa a WABA, o ID do telefone da unidade e o WA ID do cliente.

A partir da raiz do projeto, com o ambiente Python do chatbot:

```bash
python -m utilitarios.monitoring.blocked_users blocked-users
```

O relatório distingue bloqueios nos dois lados, somente na Meta e somente no banco. Mostra separadamente falhas de consulta e vínculos de unidade divergentes. Falha de uma unidade deixa seus contatos locais sem comparação e permite verificar as demais.

O subcomando acima mascara o WA ID. Para ver o número completo, acrescente `--show-wa-id`. Executar o arquivo diretamente sem argumentos mantém o atalho local que exibe os números completos. O subcomando retorna 0 quando os dados conferem, 1 quando há divergência e 2 quando ocorre erro de coleta ou execução.

A ferramenta usa as configurações do `.env` da raiz, com as substituições de `LOCAL_ENV` no arquivo privado `utilitarios/local_settings.py`. O [bootstrap](bootstrap.py) carrega esse ambiente antes das conexões.

O bloqueio de clientes pelo chatbot usa as [operações da Meta](../core/integrations/whatsapp/tools/usuarios.py) e os [registros locais](../core/repositories/seguranca/bloqueio_meta.py). Para desbloquear um cliente cadastrado, o [Django Admin](../callback/webhook/admin.py) solicita o desbloqueio na Meta antes de excluir o registro local da unidade.
