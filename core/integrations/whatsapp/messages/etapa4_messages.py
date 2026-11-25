"""Lista de assuntos apresentada após confirmar o produto; roteiro aprovado."""

MENSAGEM_ASSUNTO = "Certo, sobre qual assunto você quer falar? Selecione apenas uma opção."
MENSAGEM_ASSUNTO_INVALIDO = "Olha, não consegui entender. Sobre qual assunto você quer falar?"
OPCOES_ASSUNTO = (
    ("Previsão de entrega", "entrega", "Quero falar sobre a previsão de entrega do meu produto"),
    ("Avarias no produto", "assistencia", "Meu produto veio com avarias"),
    ("Preciso de um montador", "montador", None),
    ("Dois ou mais assuntos", "misto", "Duas ou mais opções acima"),
    ("Outros", "outros", None),
)
