"""Calculos do painel do Guardiao (Fase 2, ver PROJETO.md secao 9).

Funcoes puras: recebem o documento de memoria (o mesmo dict que memoria.py
le/grava) e devolvem dados prontos pra tela. Nao tocam banco, nao importam
streamlit, pra dar pra testar isolado com um doc sintetico.
"""

import calendar
import datetime

CATEGORIAS_GASTO = ["necessidade", "desejo", "impulso", "mercado"]


def _hoje(hoje=None):
    return hoje or datetime.date.today()


def _parse_data(texto):
    try:
        return datetime.date.fromisoformat(str(texto)[:10])
    except (ValueError, TypeError):
        return None


def _mes_atual_str(hoje):
    return hoje.isoformat()[:7]


def _compras_do_mes(memoria, hoje):
    """So compras com preco de verdade (ignora registros de decisao do botao
    'Vou comprar', que nao tem preco/categoria, so resumo e data).
    """
    mes = _mes_atual_str(hoje)
    return [
        c
        for c in memoria.get("compras", [])
        if isinstance(c, dict) and str(c.get("data", "")).startswith(mes) and c.get("preco")
    ]


def calcular_termometro(memoria, hoje=None):
    """Bloco 1: gasto do mes vs limite, dias restantes no mes."""
    hoje = _hoje(hoje)
    limite = memoria.get("perfil", {}).get("limite_mensal")
    gasto_mes = sum(float(c.get("preco") or 0) for c in _compras_do_mes(memoria, hoje))
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
    resultado = {
        "limite_definido": bool(limite),
        "limite": float(limite) if limite else None,
        "gasto_mes": gasto_mes,
        "dias_restantes": ultimo_dia - hoje.day,
        "percentual": None,
        "estourou": False,
    }
    if limite:
        resultado["percentual"] = min(gasto_mes / limite, 1.0)
        resultado["estourou"] = gasto_mes > limite
    return resultado


def calcular_gasto_diario(memoria, hoje=None):
    """Gasto por dia do mes atual, pro grafico de barras do painel.
    Devolve uma lista com um valor por dia do mes (indice 0 = dia 1).
    """
    hoje = _hoje(hoje)
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
    por_dia = [0.0] * ultimo_dia
    for c in _compras_do_mes(memoria, hoje):
        d = _parse_data(c.get("data"))
        if d:
            por_dia[d.day - 1] += float(c.get("preco") or 0)
    return {"dias": por_dia, "dia_hoje": hoje.day}


def calcular_origem_gasto(memoria, hoje=None):
    """Bloco 2: de onde veio o gasto do mes, dividido por categoria."""
    hoje = _hoje(hoje)
    compras = _compras_do_mes(memoria, hoje)
    total = sum(float(c.get("preco") or 0) for c in compras)
    por_categoria = {cat: 0.0 for cat in CATEGORIAS_GASTO}
    for c in compras:
        cat = c.get("categoria")
        if cat in por_categoria:
            por_categoria[cat] += float(c.get("preco") or 0)
    fatias = [
        {
            "categoria": cat,
            "valor": por_categoria[cat],
            "percentual": (por_categoria[cat] / total) if total else 0.0,
        }
        for cat in CATEGORIAS_GASTO
    ]
    return {"total": total, "fatias": fatias, "tem_dado": total > 0}


def calcular_dinheiro_segurado(memoria):
    """Bloco 3: soma de (cotacao mais cara vista - preco pago) por item
    comprado, so quando isso deu positivo (a pessoa pagou menos do que a
    pior cotacao que ela mesma viu). E o numero de prova de valor do produto.
    """
    itens = []
    total = 0.0
    for c in memoria.get("compras", []):
        if not isinstance(c, dict):
            continue
        cotacoes = c.get("cotacoes") or []
        if not cotacoes:
            continue
        try:
            preco_pago = float(c.get("preco") or 0)
        except (TypeError, ValueError):
            continue
        maior_cotacao = max(
            (float(q.get("preco", 0)) for q in cotacoes if isinstance(q, dict)),
            default=0.0,
        )
        economia = maior_cotacao - preco_pago
        if economia > 0:
            itens.append(
                {
                    "item": c.get("item"),
                    "preco_pago": preco_pago,
                    "maior_cotacao": maior_cotacao,
                    "economia": economia,
                }
            )
            total += economia
    itens.sort(key=lambda i: i["economia"], reverse=True)
    return {"total": total, "itens": itens, "tem_dado": bool(itens)}


def _padrao_impulso(compras_com_preco):
    total = len(compras_com_preco)
    if total < 3:
        return {
            "chave": "impulso",
            "titulo": "Comprador por impulso",
            "pronto": False,
            "minimo": 3,
            "progresso": total,
        }
    impulsivas = [c for c in compras_com_preco if c.get("categoria") == "impulso"]
    return {
        "chave": "impulso",
        "titulo": "Comprador por impulso",
        "pronto": True,
        "percentual": len(impulsivas) / total,
        "quantidade": len(impulsivas),
        "total": total,
    }


def _padrao_abandono(compras_com_preco):
    avaliadas = [c for c in compras_com_preco if c.get("resultado")]
    if len(avaliadas) < 3:
        return {
            "chave": "abandono",
            "titulo": "Compra e abandona",
            "pronto": False,
            "minimo": 3,
            "progresso": len(avaliadas),
        }
    ruins = [c for c in avaliadas if c.get("resultado") in ("arrependimento", "nao_uso")]
    return {
        "chave": "abandono",
        "titulo": "Compra e abandona",
        "pronto": True,
        "percentual": len(ruins) / len(avaliadas),
        "quantidade": len(ruins),
        "total": len(avaliadas),
    }


def _meses_entre(inicio, fim):
    return (fim.year - inicio.year) * 12 + (fim.month - inicio.month)


def _padrao_parcelas(memoria, hoje):
    """Parcelamentos ainda ativos hoje (parcelas restantes > 0) e quanto
    disso compromete o mes que vem. Matematica direta, ativa com 1 compra
    parcelada so, sem precisar de volume.
    """
    limite = memoria.get("perfil", {}).get("limite_mensal")
    ativas = []
    compromisso_mensal = 0.0
    for c in memoria.get("compras", []):
        if not isinstance(c, dict) or c.get("forma_pagamento") != "parcelado":
            continue
        parcelas = c.get("parcelas")
        preco = c.get("preco")
        data_compra = _parse_data(c.get("data"))
        if not parcelas or not preco or not data_compra:
            continue
        parcela_valor = float(preco) / int(parcelas)
        parcelas_pagas = min(int(parcelas), _meses_entre(data_compra, hoje) + 1)
        restantes = int(parcelas) - parcelas_pagas
        if restantes > 0:
            ativas.append(
                {
                    "item": c.get("item"),
                    "parcela_mensal": parcela_valor,
                    "parcelas_restantes": restantes,
                }
            )
            compromisso_mensal += parcela_valor
    return {
        "chave": "parcelas",
        "titulo": "Gasta além do que pode",
        "pronto": bool(ativas),
        "compromisso_mensal": compromisso_mensal,
        "parcelas_ativas": ativas,
        "percentual_do_limite": (compromisso_mensal / limite) if limite else None,
    }


def _padrao_cruzamento(compras_com_preco):
    avaliadas = [
        c for c in compras_com_preco if c.get("categoria") == "impulso" and c.get("resultado")
    ]
    if len(avaliadas) < 5:
        return {
            "chave": "cruzamento",
            "titulo": "Impulso e arrependimento",
            "pronto": False,
            "minimo": 5,
            "progresso": len(avaliadas),
        }
    ruins = [c for c in avaliadas if c.get("resultado") in ("arrependimento", "nao_uso")]
    return {
        "chave": "cruzamento",
        "titulo": "Impulso e arrependimento",
        "pronto": True,
        "percentual": len(ruins) / len(avaliadas),
        "quantidade": len(ruins),
        "total": len(avaliadas),
    }


def _padrao_recorrencia(memoria):
    """Preco subindo ou intervalo de recompra encurtando, so em item de uso
    continuo (senao duas compras de coisas diferentes por acaso homonimas
    contariam como recorrencia).
    """
    por_item = {}
    for p in memoria.get("precos", []):
        if not isinstance(p, dict) or not p.get("uso_continuo"):
            continue
        chave = str(p.get("item", "")).strip().lower()
        if chave:
            por_item.setdefault(chave, []).append(p)

    itens_prontos = []
    for registros in por_item.values():
        if len(registros) < 2:
            continue
        ordenados = sorted(registros, key=lambda r: r.get("data", ""))
        datas = [_parse_data(r.get("data")) for r in ordenados]
        if any(d is None for d in datas):
            continue
        precos = [float(r.get("preco") or 0) for r in ordenados]

        subindo = precos[-1] > precos[0]
        encurtando = None
        if len(datas) >= 3:
            intervalo_atual = (datas[-1] - datas[-2]).days
            intervalo_anterior = (datas[-2] - datas[-3]).days
            encurtando = intervalo_atual < intervalo_anterior

        if subindo or encurtando:
            itens_prontos.append(
                {
                    "item": ordenados[-1].get("item"),
                    "preco_inicial": precos[0],
                    "preco_atual": precos[-1],
                    "subindo": subindo,
                    "intervalo_encurtando": encurtando,
                }
            )
    return {
        "chave": "recorrencia",
        "titulo": "Recorrência esticando",
        "pronto": bool(itens_prontos),
        "itens": itens_prontos,
    }


def _padrao_cacador(dinheiro_segurado):
    """Mesmo numero do bloco 3, sem minimo adicional: e so a vitrine dele
    dentro da secao de padroes.
    """
    return {
        "chave": "cacador",
        "titulo": "Caçador de preço bom",
        "pronto": dinheiro_segurado["tem_dado"],
        "total_economizado": dinheiro_segurado["total"],
        "quantidade_itens": len(dinheiro_segurado["itens"]),
    }


def calcular_padroes(memoria, hoje=None, dinheiro_segurado=None):
    hoje = _hoje(hoje)
    compras_com_preco = [
        c for c in memoria.get("compras", []) if isinstance(c, dict) and c.get("preco")
    ]
    if dinheiro_segurado is None:
        dinheiro_segurado = calcular_dinheiro_segurado(memoria)
    return [
        _padrao_impulso(compras_com_preco),
        _padrao_abandono(compras_com_preco),
        _padrao_parcelas(memoria, hoje),
        _padrao_cruzamento(compras_com_preco),
        _padrao_recorrencia(memoria),
        _padrao_cacador(dinheiro_segurado),
    ]


def montar_painel(memoria, hoje=None):
    hoje = _hoje(hoje)
    dinheiro_segurado = calcular_dinheiro_segurado(memoria)
    return {
        "termometro": calcular_termometro(memoria, hoje),
        "origem_gasto": calcular_origem_gasto(memoria, hoje),
        "gasto_diario": calcular_gasto_diario(memoria, hoje),
        "dinheiro_segurado": dinheiro_segurado,
        "padroes": calcular_padroes(memoria, hoje, dinheiro_segurado),
    }
