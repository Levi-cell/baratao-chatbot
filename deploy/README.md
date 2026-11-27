# Implantação do Baratão na VM Ubuntu

O webhook serve a API, o Admin e o painel. O worker de fluxo processa o atendimento de sete etapas. O worker de consumo atualiza os dados de cobrança da Meta.

## Instalação inicial

Clone a branch `prod` como o usuario `ubuntu` e instale as dependencias:

```bash
git clone --branch prod --single-branch git@github.com:Levi-cell/baratao-chatbot.git /opt/chatbot/app
python3 -m venv /opt/chatbot/venv
/opt/chatbot/venv/bin/pip install --upgrade pip
/opt/chatbot/venv/bin/pip install -r /opt/chatbot/app/requirements.txt
```

Crie `/etc/chatbot/chatbot.env` conforme o procedimento em
[`regras_deploy/modificando_env_e_banco_em_prod.md`](../regras_deploy/modificando_env_e_banco_em_prod.md),
sem registrar segredos no repositorio. Em producao, use `DJANGO_DEBUG=False`,
configure o dominio em `DJANGO_ALLOWED_HOSTS` e mantenha o arquivo restrito:

```bash
sudo chown root:chatbot /etc/chatbot/chatbot.env
sudo chmod 0640 /etc/chatbot/chatbot.env
```

Configure o RDS com TLS e informe o
endpoint do Redis remoto em `REDIS_HOST`. A aplicacao nao usa nem exige um
`redis-server` local na VM. Mantenha `PGSSLCERTMODE=disable` quando o RDS
autenticar por usuario/senha. Essa opcao desativa apenas o certificado TLS de
cliente; use `DB_SSLMODE=verify-full` e `DB_SSLROOTCERT` para continuar
validando o certificado do servidor.

Se o banco estiver vazio, crie antes o schema de destino no DBeaver:

```sql
CREATE SCHEMA IF NOT EXISTS chatbot;
```

Depois, prepare o Django. Suas migrations criam `chatbot.auth_user`, necessária
antes do DDL de negócio por causa do vínculo de monitoramento:

```bash
sudo -u chatbot bash -c 'set -a; source /etc/chatbot/chatbot.env; set +a; cd /opt/chatbot/app; export PYTHONPATH=/opt/chatbot/app; /opt/chatbot/venv/bin/python callback/manage.py check --deploy'
sudo -u chatbot bash -c 'set -a; source /etc/chatbot/chatbot.env; set +a; cd /opt/chatbot/app; export PYTHONPATH=/opt/chatbot/app; /opt/chatbot/venv/bin/python callback/manage.py migrate --noinput'
sudo -u chatbot bash -c 'set -a; source /etc/chatbot/chatbot.env; set +a; cd /opt/chatbot/app; export PYTHONPATH=/opt/chatbot/app; /opt/chatbot/venv/bin/python callback/manage.py collectstatic --noinput'
```

`EnvironmentFile` é carregado automaticamente somente pelo systemd. Uma sessão
SSH comum não recebe essas variáveis; os comandos manuais acima carregam o mesmo
arquivo privado dos serviços sem exibir seu conteúdo.

Em uma instalação vazia, após as migrations do Django, siga o
[setup do banco de negócio](../core/database/README.md#instalação-em-um-schema-preparado) antes de iniciar
os serviços. Na atualização de um banco existente, use a migração incremental
específica, sem executar novamente o setup como substituto da migração.

## Serviços da aplicação

Os serviços usados pelo Baratão são webhook/painel, worker de fluxo e worker de consumo Meta. Os arquivos em [deploy/systemd](systemd) definem os executáveis, o usuário, o diretório e o arquivo de ambiente. A VM usa PostgreSQL e Redis remotos. Ao instalar ou alterar uma unidade, copiar o arquivo correspondente para `/etc/systemd/system/` e executar `systemctl daemon-reload`. Habilitar somente integrações configuradas para aquela instalação. A [rotina de deploy](../regras_deploy/rotina_deploy.md) registra a ordem de pausa e retomada.

## Habilitar o Nginx e HTTPS

Instale o template, substitua `__DOMAIN__` pelo dominio real e habilite o site.
O Gunicorn escuta somente em `127.0.0.1:8000`; apenas o Nginx recebe trafego
publico.

```bash
sudo install -m 0644 /opt/chatbot/app/deploy/nginx/chatbot-log-format.conf /etc/nginx/conf.d/chatbot-log-format.conf
sudo install -m 0644 /opt/chatbot/app/deploy/nginx/chatbot.conf /etc/nginx/sites-available/chatbot
sudoedit /etc/nginx/sites-available/chatbot
sudo ln -sfn /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/chatbot
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Com o DNS apontando para o IP estatico e as portas 80/443 abertas, deixe o
Certbot criar a configuracao HTTPS somente depois de emitir o certificado:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx --redirect -d SEU_DOMINIO
sudo certbot renew --dry-run
```

Somente depois de o HTTPS funcionar, ative no ambiente
`DJANGO_TRUST_X_FORWARDED_PROTO=True`, `DJANGO_SECURE_SSL_REDIRECT=True`,
`DJANGO_SESSION_COOKIE_SECURE=True` e `DJANGO_CSRF_COOKIE_SECURE=True`, e
reinicie o webhook. O Nginx sobrescreve `X-Forwarded-Proto`; o Django nao confia
em um valor enviado diretamente pelo cliente.

## Banco existente

A Beta V0.3.0 acrescenta a [migração da conferência de CPF](migrations/20261127_contato_conferencia_cpf.sql) sobre a V0.2.1. O catálogo tem 7 etapas e 21 transições. Os procedimentos abaixo servem a bases em estados anteriores. Identifique a origem antes de escolher o script. [Estado do banco e histórico](../core/database/README.md#catálogo-de-produção)

Para o banco que já concluiu a migração das nove etapas com WAAC e BSUID, pause os serviços da aplicação e execute o [SQL das sete etapas](migrations/20261126_baratao_sete_etapas.sql) no DBeaver. A conferência retorna 7 etapas, 28 transições e 90 dias de bloqueio na etapa final. Em seguida, aplicar o [SQL de recoleta](migrations/20261126_recoleta_titular.sql), que retira o atalho para produto e deixa 27 transições. Na Beta V0.2.0, o [SQL de repetição por mídia](migrations/20261127_midia_repete_etapa.sql) remove as seis arestas de mídia e confere as 21 transições. O script pode ser reaplicado na base de sete etapas. O código e o catálogo devem corresponder à mesma versão. Para outra versão de origem, consulte o [histórico das migrações](../core/database/README.md).

Os procedimentos de ambiente e acesso ao banco estão no [guia de configuração](../regras_deploy/modificando_env_e_banco_em_prod.md).

## Testes na VM

[Executar a suíte de varejo em PostgreSQL isolado](../AMBIENTE_DESENVOLVIMENTO.md).
