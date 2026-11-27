-- A carga do TXT e a criação da tabela compartilham a transação de catalogo_produtos.py.
CREATE TABLE IF NOT EXISTS chatbot.catalogo (
    codigo_produto integer PRIMARY KEY CHECK (codigo_produto > 0),
    nome_produto text NOT NULL CHECK (btrim(nome_produto) <> ''),
    categoria text NOT NULL CHECK (categoria IN ('moveis', 'estofado'))
);
