"""O cerebro do Guardiao: fala com o modelo da Anthropic.

Usa cache de prompt para nao reenviar, a preco cheio, a parte que se repete a
cada mensagem. O metodo (fixo) e o historico ja conversado entram em cache e
custam ~10% na releitura. So a memoria atual e o turno novo pagam preco cheio.
"""

import datetime
import json
import os
import re

import anthropic

from . import memoria as mem
from .metodo import METODO

# Usado so pela rede de seguranca: detecta se a resposta trouxe um
# diagnostico (os tres rotulos), para o caso do modelo esquecer de chamar
# salvar_memoria naquele turno.
_TEM_DIAGNOSTICO = re.compile(r"Motivação da compra\s*:\s*(.*?)(?:\n|$)")

# Modelo padrao. Para baratear, defina GUARDIAO_MODELO=claude-sonnet-5 no .env.
MODELO = os.environ.get("GUARDIAO_MODELO", "claude-opus-4-8")

_cliente = None


def _get_cliente():
    global _cliente
    if _cliente is None:
        _cliente = anthropic.Anthropic()
    return _cliente


# A unica ferramenta: gravar o documento de memoria atualizado.
FERRAMENTA_MEMORIA = {
    "name": "salvar_memoria",
    "description": (
        "Grava o documento de memoria atualizado da pessoa. Envie o documento "
        "INTEIRO ja atualizado (perfil, necessidades, desejos, compras, analises), "
        "mantendo o que ja existia e acrescentando o novo. Use sempre que aprender "
        "algo duravel: uma prioridade, uma necessidade, um desejo, uma compra feita, "
        "ou o veredito que voce deu."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "memoria_json": {
                "type": "string",
                "description": (
                    "O documento de memoria completo, como uma string JSON com as "
                    "chaves perfil, necessidades, desejos, compras e analises."
                ),
            }
        },
        "required": ["memoria_json"],
    },
}


def _montar_mensagens(usuario_id, memoria, desde_id=0):
    """Monta as mensagens da API com cache no historico ja conversado.

    So entram as mensagens desta sessao (desde_id). A continuidade entre
    sessoes vem da memoria persistente, nao do rolo antigo de mensagens.
    O turno atual do usuario recebe, junto, a memoria atual (parte volatil,
    que muda toda vez e por isso fica fora do cache).
    """
    hist = mem.ler_mensagens(usuario_id, desde_id)
    mensagens = [{"role": m["papel"], "content": m["conteudo"]} for m in hist]

    # Cacheia todo o historico ja concluido: marca o ultimo bloco da penultima
    # mensagem. A ultima mensagem e o turno atual do usuario, que muda sempre.
    if len(mensagens) >= 2:
        anterior = mensagens[-2]
        anterior["content"] = [
            {
                "type": "text",
                "text": anterior["content"],
                "cache_control": {"type": "ephemeral"},
            }
        ]

    # Injeta a memoria atual junto ao turno atual do usuario (sem cache).
    # A data de hoje vai junto: sem isso o modelo nao tem como saber se uma
    # pendencia registrada e antiga (para o follow-up proativo).
    if mensagens and mensagens[-1]["role"] == "user":
        hoje = datetime.date.today().isoformat()
        memoria_txt = (
            f"HOJE E: {hoje}\n\n"
            "MEMÓRIA ATUAL DA PESSOA (leia antes de responder):\n"
            + json.dumps(memoria, ensure_ascii=False, indent=2)
        )
        mensagens[-1]["content"] = [
            {"type": "text", "text": memoria_txt},
            {"type": "text", "text": hist[-1]["conteudo"]},
        ]

    return mensagens


def responder(usuario_id, modelo=None, desde_id=0):
    """Gera a resposta do Guardiao para o estado atual da conversa.

    desde_id limita o contexto enviado ao modelo as mensagens desta sessao.
    """
    cliente = _get_cliente()
    modelo = modelo or MODELO
    memoria = mem.ler_memoria(usuario_id)

    # O metodo e fixo: vira um bloco em cache, reusado em toda chamada.
    system = [{"type": "text", "text": METODO, "cache_control": {"type": "ephemeral"}}]
    mensagens = _montar_mensagens(usuario_id, memoria, desde_id)

    partes_texto = []
    salvou_memoria = False

    # Laco curto: o modelo responde e, no caminho, pode chamar salvar_memoria.
    for _ in range(5):
        resposta = cliente.messages.create(
            model=modelo,
            # 2000 (era 700, depois 1200): turnos que combinam duplicata ou
            # follow-up de pendencia + os ate 5 rotulos ainda estavam cortando
            # a resposta no meio antes de terminar.
            max_tokens=2000,
            system=system,
            tools=[FERRAMENTA_MEMORIA],
            messages=mensagens,
        )

        for bloco in resposta.content:
            if bloco.type == "text" and bloco.text.strip():
                partes_texto.append(bloco.text)

        if resposta.stop_reason != "tool_use":
            break

        mensagens.append({"role": "assistant", "content": resposta.content})
        resultados = []
        for bloco in resposta.content:
            if bloco.type == "tool_use" and bloco.name == "salvar_memoria":
                ok = _aplicar_salvar_memoria(usuario_id, bloco.input)
                salvou_memoria = salvou_memoria or ok
                resultados.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": bloco.id,
                        "content": "memoria atualizada" if ok else "nao consegui ler o JSON",
                        "is_error": not ok,
                    }
                )
        mensagens.append({"role": "user", "content": resultados})

    texto_final = (
        "\n\n".join(partes_texto).strip()
        or "Estou aqui. Me conta o que você está pensando em comprar."
    )

    # Rede de seguranca: a memoria e o diferencial do produto, entao nao pode
    # depender so do modelo lembrar de chamar a ferramenta. Se a resposta deu
    # um diagnostico e nenhum salvamento aconteceu neste turno, registra pelo
    # menos o essencial. A "Motivação da compra" so explica o porque (ex:
    # "necessidade real"), entao juntamos com a ultima fala da pessoa, que
    # normalmente cita o produto, senao o item registrado fica sem nome.
    if not salvou_memoria:
        encontrado = _TEM_DIAGNOSTICO.search(texto_final)
        if encontrado:
            ultima_fala = _ultima_fala_do_usuario(usuario_id, desde_id)
            _salvar_fallback_diagnostico(usuario_id, encontrado.group(1).strip(), ultima_fala)

    return texto_final


def _aplicar_salvar_memoria(usuario_id, entrada):
    """Le o JSON enviado pelo modelo e grava na memoria. Devolve True se deu certo."""
    bruto = entrada.get("memoria_json", "")
    try:
        doc = json.loads(bruto)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(doc, dict):
        return False
    mem.salvar_memoria(usuario_id, doc)
    return True


def _classificar_motivacao(motivacao):
    """Heuristica simples para a rede de seguranca: decide necessidades ou
    desejos pelo proprio texto da motivacao, sem precisar de outra chamada
    ao modelo. Usa as expressoes que o Guardiao mesmo costuma escrever.
    """
    texto = motivacao.lower()
    if "necessidade" in texto:
        return "necessidades"
    if "desejo" in texto or "vontade" in texto:
        return "desejos"
    return None


def _ultima_fala_do_usuario(usuario_id, desde_id):
    """Ultima mensagem que a pessoa escreveu nesta sessao. Normalmente cita o
    produto de verdade, o que a "Motivação da compra" sozinha nao traz.
    """
    hist = mem.ler_mensagens(usuario_id, desde_id)
    for m in reversed(hist):
        if m["papel"] == "user":
            return m["conteudo"]
    return ""


def _salvar_fallback_diagnostico(usuario_id, motivacao, ultima_fala=""):
    """Rede de seguranca: registra pelo menos o essencial quando o modelo deu
    um diagnostico mas esqueceu de chamar salvar_memoria nesse turno. Tenta
    classificar em necessidades ou desejos em vez de despejar tudo em
    analises sem criterio, e junta a fala da pessoa pro item ter nome.
    """
    doc = mem.ler_memoria(usuario_id)
    observacao = "Registrado automaticamente, o modelo não salvou nesse turno."
    item = ultima_fala.strip() or motivacao
    lista = _classificar_motivacao(motivacao)
    if lista:
        doc.setdefault(lista, []).append(
            {"item": item, "detalhe": motivacao, "observacao": observacao}
        )
    else:
        doc.setdefault("analises", []).append(
            {"resumo": item, "detalhe": motivacao, "observacao": observacao}
        )
    mem.salvar_memoria(usuario_id, doc)
