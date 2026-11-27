# Testes do Baratão na VM Ubuntu

Os testes do projeto rodam na VM Ubuntu. Com a revisão a validar em `/opt/chatbot/app`, Python 3.12 em `/opt/chatbot/venv`, as dependências de `requirements.txt` instaladas e o PostgreSQL de teste disponível pelo pacote `postgresql-common` (com o servidor e o cliente instalados), execute:

```bash
cd /opt/chatbot/app
sudo -u chatbot bash deploy/testar_ubuntu.sh
```

O script usa `pg_virtualenv` para criar um cluster temporário. As duas suítes que recriam o schema usam bancos separados nesse cluster. O processo recebe credenciais de ensaio e usa transporte Meta simulado. É possível selecionar outro ambiente Python com `BARATAO_PYTHON`. [Script](deploy/testar_ubuntu.sh)

## Serviços e certificado

Os serviços leem `/etc/chatbot/chatbot.env`. Para o RDS, configure `DB_SSLMODE=verify-full` e `DB_SSLROOTCERT=/etc/ssl/certs/aws-rds-global-bundle.pem`. O arquivo PEM precisa conter a CA do RDS e ser legível pelo usuário `chatbot`. A suíte isolada usa seu próprio PostgreSQL na VM. [Configuração de implantação](regras_deploy/modificando_env_e_banco_em_prod.md)
