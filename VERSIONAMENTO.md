# Versionamento do Baratão

## Histórico de versões

### Versão beta — Triagem e encaminhamento do pós-venda

Commit: PENDENTE

## Padrão de numeração

Adotamos o formato `VMAJOR.MINOR.PATCH`, seguindo o versionamento semântico.
O prefixo V identifica a versão; cada um dos três números tem um significado:

1. **MAJOR** (primeiro número): mudança incompatível com os contratos públicos
   existentes. Exemplo: V1.2.0 -> V2.0.0.
2. **MINOR** (segundo número): funcionalidade nova ou melhoria substancial mantendo
   compatibilidade. Exemplo: V1.1.1 -> V1.2.0.
3. **PATCH** (terceiro número): correção de falha mantendo compatibilidade.
   Exemplo: V1.2.0 -> V1.2.1.

Compatibilidade considera os contratos documentados usados pelos usuários e pelas
integrações. Uma migração interna de banco, sozinha, não exige aumentar o MAJOR.

Quando uma entrega reúne tipos diferentes de mudança, prevalece o maior impacto.
Ao aumentar o MAJOR, zerar MINOR e PATCH. Ao aumentar o MINOR, zerar PATCH.
Os números são independentes, não decimais: V1.9.0 pode avançar para V1.10.0.
Não é necessário publicar V1.1.2 antes de V1.2.0; a mudança determina qual número
avança. Evitar saltos arbitrários, como V1.1.1 -> V1.5.0, sem motivo documentado.

Cada correção publicada recebe uma versão PATCH. Novidades seguem a regra MINOR ou MAJOR. Cada versão publicada identifica um único commit.

Referência: [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## Registro das próximas versões

1. Antes do commit, registrar a versão e uma descrição de até seis palavras com o campo `Commit: PENDENTE`.
2. Criar o commit da versão e publicá-lo na branch `prod`.
3. Após confirmar a publicação, preencher localmente o hash completo do commit.
4. Enviar esse registro de hash junto com a versão seguinte.
