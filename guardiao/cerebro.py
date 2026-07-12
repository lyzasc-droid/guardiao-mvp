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
        "INTEIRO ja atualizado (perfil, necessidades, desejos, compras, analises, "
        "lista_mercado, precos), mantendo o que ja existia e acrescentando o novo. "
        "Use sempre que aprender algo duravel: uma prioridade, uma necessidade, um "
        "desejo, uma compra feita, ou o veredito que voce deu. Para lista de "
        "mercado use atualizar_lista_mercado; para precos use registrar_preco."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "memoria_json": {
                "type": "string",
                "description": (
                    "O documento de memoria completo, como uma string JSON com as "
                    "chaves perfil, necessidades, desejos, compras, analises, "
                    "lista_mercado e precos."
                ),
            }
        },
        "required": ["memoria_json"],
    },
}

# Ferramenta leve da lista de mercado: mexe SO na lista, sem reescrever o
# documento de memoria inteiro. Anotar "arroz" custava a reescrita de toda a
# memoria em tokens de saida (a parte mais cara); com esta ferramenta a saida
# do modelo e so a acao e os itens.
#
# Limite de tamanho por item (ver _aplicar_lista_mercado): item de mercado e
# curto (1 a 3 palavras: "arroz", "sabão em pó"). Uma descricao longa e cheia
# de detalhe e sinal de que e um bem duravel (eletrodomestico, eletronico),
# nao mercado, mesmo que a pessoa tenha dito "lista". Essa checagem e um freio
# no codigo, independente do modelo seguir a instrucao do metodo ou nao.
_MAX_PALAVRAS_ITEM_MERCADO = 5
_MAX_CARACTERES_ITEM_MERCADO = 35

FERRAMENTA_LISTA_MERCADO = {
    "name": "atualizar_lista_mercado",
    "description": (
        "Adiciona ou remove itens da lista de mercado da pessoa, ou esvazia a "
        "lista. Mexe apenas na lista, o resto da memoria fica intacto. Use "
        "SOMENTE para itens curtos de reposicao do dia a dia (comida, bebida, "
        "limpeza, higiene: 'arroz', 'sabão em pó'). NUNCA use para "
        "eletrodomestico, eletronico, movel ou qualquer bem duravel, mesmo que "
        "a pessoa diga a palavra 'lista' -- itens assim sao rejeitados e "
        "precisam ir pelo diagnostico normal (necessidades/desejos). NUNCA use "
        "salvar_memoria pra mexer na lista de mercado."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "acao": {
                "type": "string",
                "enum": ["adicionar", "remover", "limpar"],
                "description": "O que fazer com os itens.",
            },
            "itens": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Itens em minusculas, um por elemento (ex: ['arroz', 'sabão em pó']). "
                    "Obrigatorio para adicionar e remover; ignorado em limpar."
                ),
            },
        },
        "required": ["acao"],
    },
}


# Ferramenta leve de precos: preco PAGO vira referencia permanente (historico
# em doc["precos"]); preco so VISTO (cotacao) fica anotado dentro do item
# correspondente em necessidades/desejos, morrendo junto com a decisao.
# A data e sempre colocada pelo codigo, nunca pelo modelo.
FERRAMENTA_PRECO = {
    "name": "registrar_preco",
    "description": (
        "Registra um preco que a pessoa mencionou para um item concreto. "
        "acao 'pago': ela COMPROU e pagou esse valor; vira o preco de referencia "
        "permanente do item. acao 'cotacao': ela apenas VIU ou orcou esse valor "
        "para um item que esta considerando comprar; fica anotado dentro do item "
        "em necessidades/desejos. A data de hoje e adicionada automaticamente. "
        "Nunca invente valor nem local: registre somente o que a pessoa disse."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "acao": {
                "type": "string",
                "enum": ["pago", "cotacao"],
                "description": "pago = comprou por esse valor; cotacao = so viu o preco.",
            },
            "item": {
                "type": "string",
                "description": "Nome curto do item (ex: 'cotonete', 'vitanol').",
            },
            "preco": {
                "type": "number",
                "description": "Valor em reais.",
            },
            "local": {
                "type": "string",
                "description": "Onde pagou ou viu (mercado, farmacia, site). Omitir se a pessoa nao disse.",
            },
            "uso_continuo": {
                "type": "boolean",
                "description": (
                    "Somente para acao 'pago'. true quando o contexto indica item de uso "
                    "recorrente (remedio de uso continuo, cosmetico que ela usa sempre, "
                    "assinatura, algo que ela vai precisar repor). false ou omitido para "
                    "compra pontual/unica (eletrodomestico, movel, presente). Decida pelo "
                    "que a pessoa disse, nunca pergunte so pra preencher isso."
                ),
            },
        },
        "required": ["acao", "item", "preco"],
    },
}


def _formatar_reais(valor):
    return ("R$ %.2f" % valor).replace(".", ",")


def _referencia_do_item(doc, item):
    """Ultimo preco PAGO registrado para o item (casamento parcial, sem
    diferenciar maiuscula). E o preco de referencia vivo. None se nao houver.
    """
    chave = item.lower()
    achado = None
    for registro in doc.get("precos", []):
        nome = str(registro.get("item", "")).lower()
        if chave == nome or chave in nome or nome in chave:
            achado = registro  # a lista e cronologica, o ultimo casamento vence
    return achado


def _aplicar_registrar_preco(usuario_id, entrada):
    """Executa a ferramenta registrar_preco direto no banco. Devolve o texto de
    resultado pro modelo, ja com a comparacao contra a referencia existente,
    pra ele orientar a pessoa sem precisar calcular nada.
    """
    acao = entrada.get("acao")
    item = (entrada.get("item") or "").strip()
    local = (entrada.get("local") or "").strip()
    try:
        preco = float(entrada.get("preco"))
    except (TypeError, ValueError):
        return None
    if not item or preco <= 0 or acao not in ("pago", "cotacao"):
        return None

    doc = mem.ler_memoria(usuario_id)
    hoje = datetime.date.today().isoformat()
    referencia = _referencia_do_item(doc, item)
    onde = f" ({local})" if local else ""

    if referencia:
        contexto = (
            f" Referencia anterior: {_formatar_reais(referencia['preco'])}"
            f" em {referencia.get('local') or 'local nao informado'}, {referencia['data']}."
        )
    else:
        contexto = " Sem referencia anterior desse item."

    if acao == "pago":
        uso_continuo = bool(entrada.get("uso_continuo"))
        doc.setdefault("precos", []).append(
            {"item": item, "preco": preco, "local": local, "data": hoje, "uso_continuo": uso_continuo}
        )
        # Compra fecha o ciclo do item: sai de necessidades/desejos (as
        # cotacoes ja cumpriram o papel) e entra em compras. Tudo numa
        # chamada so, sem depender do modelo reescrever o documento inteiro.
        chave = item.lower()
        movido = None
        for lista in ("necessidades", "desejos"):
            itens = doc.get(lista, [])
            for registro in list(itens):
                nome = str(registro.get("item", "") if isinstance(registro, dict) else registro)
                n = nome.lower()
                if chave == n or chave in n or n in chave:
                    itens.remove(registro)
                    movido = nome
                    break
            if movido:
                break
        doc.setdefault("compras", []).append(
            {"item": movido or item, "preco": preco, "local": local, "data": hoje}
        )
        mem.salvar_memoria(usuario_id, doc)
        extra = f" Item '{movido}' movido de necessidades/desejos para compras." if movido else ""
        return (
            f"preco pago registrado: {item} {_formatar_reais(preco)}{onde}."
            + contexto
            + " Esse valor e a nova referencia."
            + extra
        )

    # cotacao: anexa ao item em necessidades/desejos (cria em desejos se nao existir)
    chave = item.lower()
    alvo = None
    for lista in ("necessidades", "desejos"):
        itens = doc.get(lista, [])
        for i, registro in enumerate(itens):
            nome = str(registro.get("item", "") if isinstance(registro, dict) else registro)
            n = nome.lower()
            if chave == n or chave in n or n in chave:
                if not isinstance(registro, dict):
                    registro = {"item": nome}
                    itens[i] = registro
                alvo = registro
                break
        if alvo:
            break
    if alvo is None:
        alvo = {"item": item, "observacao": "criado ao registrar uma cotação, clareza pendente"}
        doc.setdefault("desejos", []).append(alvo)
    alvo.setdefault("cotacoes", []).append({"preco": preco, "local": local, "data": hoje})
    mem.salvar_memoria(usuario_id, doc)

    outras = [c for c in alvo["cotacoes"][:-1]]
    if outras:
        listadas = "; ".join(
            f"{_formatar_reais(c['preco'])} em {c.get('local') or 'local nao informado'} ({c['data']})"
            for c in outras
        )
        contexto += f" Outras cotacoes desse item: {listadas}."
    return (
        f"cotacao registrada em '{alvo['item']}': {_formatar_reais(preco)}{onde}."
        + contexto
    )


def _parece_bem_duravel(item):
    """Heuristica de tamanho: item de mercado e curto (1 a 3 palavras). Uma
    descricao longa, cheia de detalhe, e sinal de bem duravel (eletrodomestico,
    eletronico) descrito por extenso, nao um item de reposicao do dia a dia.
    """
    return (
        len(item) > _MAX_CARACTERES_ITEM_MERCADO
        or len(item.split()) > _MAX_PALAVRAS_ITEM_MERCADO
    )


def _aplicar_lista_mercado(usuario_id, entrada):
    """Executa a acao da ferramenta atualizar_lista_mercado direto no banco.
    Devolve o texto de resultado que volta pro modelo (com a lista atualizada,
    pra ele confirmar sem precisar adivinhar).
    """
    acao = entrada.get("acao")
    itens = [i.strip() for i in entrada.get("itens", []) if isinstance(i, str) and i.strip()]
    doc = mem.ler_memoria(usuario_id)
    lista = doc.setdefault("lista_mercado", [])

    if acao == "adicionar":
        suspeitos = [i for i in itens if _parece_bem_duravel(i)]
        if suspeitos:
            return (
                "REJEITADO: "
                + ", ".join(suspeitos)
                + " parece bem duravel (eletrodomestico/eletronico/movel), nao item de "
                "mercado. Nao adicionei na lista. Trate como compra normal: faca o "
                "diagnostico com os rotulos de sempre (Motivação, Clareza, Viabilidade "
                "financeira etc), nao chame esta ferramenta de novo pra esse item."
            )
        ja_tinha = {i.lower() for i in lista}
        for item in itens:
            if item.lower() not in ja_tinha:
                lista.append(item)
                ja_tinha.add(item.lower())
    elif acao == "remover":
        tirar = {i.lower() for i in itens}
        lista[:] = [i for i in lista if i.lower() not in tirar]
    elif acao == "limpar":
        lista.clear()
    else:
        return None

    mem.salvar_memoria(usuario_id, doc)
    if lista:
        return "lista atualizada: " + ", ".join(lista)
    return "lista atualizada: vazia"


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
            tools=[FERRAMENTA_MEMORIA, FERRAMENTA_LISTA_MERCADO, FERRAMENTA_PRECO],
            messages=mensagens,
        )

        for bloco in resposta.content:
            if bloco.type == "text" and bloco.text.strip():
                # As vezes o modelo escreve a resposta, chama salvar_memoria e
                # depois escreve a MESMA frase de novo, o que aparecia duplicado
                # na tela. Ignora o texto repetido.
                if bloco.text.strip() in (p.strip() for p in partes_texto):
                    continue
                partes_texto.append(bloco.text)

        if resposta.stop_reason != "tool_use":
            break

        mensagens.append({"role": "assistant", "content": resposta.content})
        resultados = []
        for bloco in resposta.content:
            if bloco.type != "tool_use":
                continue
            if bloco.name == "salvar_memoria":
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
            elif bloco.name == "registrar_preco":
                resultado = _aplicar_registrar_preco(usuario_id, bloco.input)
                ok = resultado is not None
                salvou_memoria = salvou_memoria or ok
                resultados.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": bloco.id,
                        "content": resultado if ok else "entrada invalida (item, preco > 0 e acao pago/cotacao sao obrigatorios)",
                        "is_error": not ok,
                    }
                )
            elif bloco.name == "atualizar_lista_mercado":
                resultado = _aplicar_lista_mercado(usuario_id, bloco.input)
                # rejeitado = a chamada rodou, mas nada foi salvo (item parece
                # bem duravel). Conta como erro pro modelo tentar outro caminho,
                # e nao marca salvou_memoria (nada foi de fato gravado).
                rejeitado = isinstance(resultado, str) and resultado.startswith("REJEITADO:")
                ok = resultado is not None and not rejeitado
                salvou_memoria = salvou_memoria or ok
                resultados.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": bloco.id,
                        "content": resultado if resultado is not None else "acao invalida",
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


def _normalizar_precos(doc):
    """Rede de seguranca: mesmo com a instrucao de usar registrar_preco, o
    modelo as vezes escreve "precos" na mao via salvar_memoria, com um
    formato proprio (ex: "valor" em vez de "preco", sem "uso_continuo").
    Isso quebrava a barra lateral com KeyError em producao. Conserta o
    formato de cada registro em vez de confiar que o modelo acertou.
    """
    precos = doc.get("precos")
    if not isinstance(precos, list):
        return
    for registro in precos:
        if not isinstance(registro, dict):
            continue
        if "preco" not in registro and "valor" in registro:
            registro["preco"] = registro.pop("valor")
        try:
            registro["preco"] = float(registro.get("preco", 0))
        except (TypeError, ValueError):
            registro["preco"] = 0
        registro.setdefault("local", "")
        registro.setdefault("data", datetime.date.today().isoformat())
        registro.setdefault("uso_continuo", False)


def _aplicar_salvar_memoria(usuario_id, entrada):
    """Le o JSON enviado pelo modelo e grava na memoria. Devolve True se deu certo."""
    bruto = entrada.get("memoria_json", "")
    try:
        doc = json.loads(bruto)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(doc, dict):
        return False
    _normalizar_precos(doc)
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
