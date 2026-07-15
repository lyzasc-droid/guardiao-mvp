"""Cria ou remove contas ficticias no banco, com perfis de dado prontos pra
testar o painel financeiro em cenarios diferentes (estourado, so comeco de
uso, endividado em parcelas, etc). Nao mexe em conta de verdade nenhuma.

Uso:
    .venv/bin/python3 criar_dados_demo.py --listar
    .venv/bin/python3 criar_dados_demo.py marina equilibrado
    .venv/bin/python3 criar_dados_demo.py marina --remover
"""

import argparse
import datetime
import sys

from guardiao import memoria as mem


def _data(hoje, dias_atras):
    """Dias atras de hoje, sempre dentro do mes atual (nunca antes do dia 1),
    pra sempre cair dentro do filtro 'esse mes' do painel, nao importa que
    dia do mes o script rodar.
    """
    dia = max(1, hoje.day - dias_atras)
    return hoje.replace(day=dia).isoformat()


def _base(hoje, prioridade, guardrails, limite_mensal=None):
    doc = mem._memoria_vazia()
    doc["perfil"]["prioridade"] = prioridade
    doc["perfil"]["guardrails"] = guardrails
    if limite_mensal is not None:
        doc["perfil"]["limite_mensal"] = float(limite_mensal)
    return doc


def _perfil_equilibrado(hoje):
    doc = _base(
        hoje,
        "Não entrar em dívida. Guardar pra uma reserva de emergência.",
        ["Já pagou parcelamento demais no passado"],
        limite_mensal=5500,
    )
    doc["compras"] = [
        {"item": "vitanol", "preco": 45.0, "local": "Pague Menos", "data": _data(hoje, 13), "categoria": "necessidade", "resultado": None},
        {"item": "tênis de corrida", "preco": 280.0, "local": "Loja Esportiva", "data": _data(hoje, 12), "categoria": "desejo", "resultado": "valeu", "cotacoes": [{"preco": 340.0, "local": "concorrente", "data": _data(hoje, 13)}]},
        {"item": "fone de ouvido bluetooth", "preco": 120.0, "local": "", "data": _data(hoje, 11), "categoria": "impulso", "resultado": "arrependimento"},
        {"item": "mercado", "preco": 150.0, "local": "mercado do bairro", "data": _data(hoje, 10), "categoria": "mercado", "resultado": None},
        {"item": "camiseta estampada", "preco": 80.0, "local": "", "data": _data(hoje, 9), "categoria": "impulso", "resultado": "nao_uso"},
        {"item": "curso de inglês online", "preco": 300.0, "local": "", "data": _data(hoje, 8), "categoria": "necessidade", "resultado": "valeu"},
        {"item": "vitanol", "preco": 50.0, "local": "Farmácia São João", "data": _data(hoje, 6), "categoria": "necessidade", "resultado": None},
        {"item": "capinha de celular", "preco": 35.0, "local": "", "data": _data(hoje, 6), "categoria": "impulso", "resultado": None},
        {"item": "notebook", "preco": 2000.0, "local": "", "data": _data(hoje, 6), "categoria": "necessidade", "resultado": None, "forma_pagamento": "parcelado", "parcelas": 10},
        {"item": "mercado", "preco": 200.0, "local": "mercado do bairro", "data": _data(hoje, 5), "categoria": "mercado", "resultado": None},
        {"item": "assinatura streaming", "preco": 40.0, "local": "", "data": _data(hoje, 4), "categoria": "desejo", "resultado": "valeu"},
        {"item": "óculos de sol", "preco": 90.0, "local": "", "data": _data(hoje, 3), "categoria": "impulso", "resultado": "arrependimento"},
        {"item": "perfume importado", "preco": 180.0, "local": "", "data": _data(hoje, 2), "categoria": "impulso", "resultado": "valeu"},
        {"item": "vitanol", "preco": 56.0, "local": "Drogaria", "data": _data(hoje, 1), "categoria": "necessidade", "resultado": None},
        {"item": "sapato social", "preco": 220.0, "local": "Loja Sapataria", "data": _data(hoje, 0), "categoria": "desejo", "resultado": None, "cotacoes": [{"preco": 300.0, "local": "concorrente", "data": _data(hoje, 2)}]},
        {"item": "chaveiro decorativo", "preco": 25.0, "local": "", "data": _data(hoje, 0), "categoria": "impulso", "resultado": "valeu"},
    ]
    doc["precos"] = [
        {"item": "vitanol", "preco": 45.0, "local": "Pague Menos", "data": _data(hoje, 13), "uso_continuo": True},
        {"item": "vitanol", "preco": 50.0, "local": "Farmácia São João", "data": _data(hoje, 6), "uso_continuo": True},
        {"item": "vitanol", "preco": 56.0, "local": "Drogaria", "data": _data(hoje, 1), "uso_continuo": True},
    ]
    return doc


def _perfil_impulsivo(hoje):
    doc = _base(
        hoje,
        "Parar de comprar coisa que não usa. Segurar o cartão.",
        ["Se sente ansiosa quando compra"],
        limite_mensal=1200,
    )
    doc["compras"] = [
        {"item": "fone de ouvido", "preco": 150.0, "local": "", "data": _data(hoje, 1), "categoria": "impulso", "resultado": "arrependimento"},
        {"item": "tênis maneiro", "preco": 220.0, "local": "", "data": _data(hoje, 2), "categoria": "impulso", "resultado": "nao_uso"},
        {"item": "óculos escuro", "preco": 90.0, "local": "", "data": _data(hoje, 3), "categoria": "impulso", "resultado": "arrependimento"},
        {"item": "jogo de videogame", "preco": 250.0, "local": "", "data": _data(hoje, 4), "categoria": "impulso", "resultado": "valeu"},
        {"item": "camisa de marca", "preco": 140.0, "local": "", "data": _data(hoje, 5), "categoria": "impulso", "resultado": "arrependimento"},
        {"item": "perfume", "preco": 200.0, "local": "", "data": _data(hoje, 6), "categoria": "impulso", "resultado": "valeu"},
        {"item": "assinatura de app", "preco": 30.0, "local": "", "data": _data(hoje, 7), "categoria": "desejo", "resultado": "valeu"},
        {"item": "mercado", "preco": 180.0, "local": "mercado do bairro", "data": _data(hoje, 8), "categoria": "mercado", "resultado": None},
        {"item": "suplemento vitamínico", "preco": 80.0, "local": "", "data": _data(hoje, 9), "categoria": "necessidade", "resultado": "valeu"},
        {"item": "suplemento vitamínico", "preco": 85.0, "local": "", "data": _data(hoje, 2), "categoria": "necessidade", "resultado": "valeu"},
    ]
    doc["precos"] = [
        {"item": "suplemento vitamínico", "preco": 80.0, "local": "", "data": _data(hoje, 9), "uso_continuo": True},
        {"item": "suplemento vitamínico", "preco": 85.0, "local": "", "data": _data(hoje, 2), "uso_continuo": True},
    ]
    return doc


def _perfil_endividado(hoje):
    doc = _base(
        hoje,
        "Sair das dívidas. Não atrasar nenhuma parcela.",
        ["Tô pagando cartão e financiamento ao mesmo tempo"],
        limite_mensal=2000,
    )
    doc["compras"] = [
        {"item": "geladeira nova", "preco": 1800.0, "local": "", "data": _data(hoje, 10), "categoria": "necessidade", "resultado": None, "forma_pagamento": "parcelado", "parcelas": 12},
        {"item": "celular novo", "preco": 1500.0, "local": "", "data": _data(hoje, 5), "categoria": "necessidade", "resultado": None, "forma_pagamento": "parcelado", "parcelas": 6},
        {"item": "mercado", "preco": 220.0, "local": "mercado do bairro", "data": _data(hoje, 1), "categoria": "mercado", "resultado": None},
        {"item": "mercado", "preco": 190.0, "local": "mercado do bairro", "data": _data(hoje, 6), "categoria": "mercado", "resultado": None},
        {"item": "remédio de uso contínuo", "preco": 60.0, "local": "", "data": _data(hoje, 9), "categoria": "necessidade", "resultado": "valeu"},
        {"item": "remédio de uso contínuo", "preco": 65.0, "local": "", "data": _data(hoje, 1), "categoria": "necessidade", "resultado": "valeu"},
        {"item": "presente de aniversário", "preco": 90.0, "local": "", "data": _data(hoje, 3), "categoria": "desejo", "resultado": "valeu"},
        {"item": "assinatura de academia", "preco": 100.0, "local": "", "data": _data(hoje, 8), "categoria": "desejo", "resultado": "nao_uso"},
    ]
    doc["precos"] = [
        {"item": "remédio de uso contínuo", "preco": 60.0, "local": "", "data": _data(hoje, 9), "uso_continuo": True},
        {"item": "remédio de uso contínuo", "preco": 65.0, "local": "", "data": _data(hoje, 1), "uso_continuo": True},
    ]
    return doc


def _perfil_iniciante(hoje):
    doc = _base(
        hoje,
        "Ainda entendendo pra onde vai o dinheiro.",
        ["nenhum guardrail declarado ainda"],
    )
    doc["compras"] = [
        {"item": "fone de ouvido simples", "preco": 60.0, "local": "", "data": _data(hoje, 1), "categoria": "impulso", "resultado": None},
        {"item": "lanche por delivery", "preco": 35.0, "local": "", "data": _data(hoje, 0), "categoria": "impulso", "resultado": None},
    ]
    return doc


PERFIS = {
    "equilibrado": (_perfil_equilibrado, "Mix saudável de necessidade/desejo/impulso, dentro do limite, com cotações e parcelamento ativo. Todos os padrões desbloqueados."),
    "impulsivo": (_perfil_impulsivo, "Maioria das compras por impulso, estourou o limite, sem parcelas nem cotações registradas."),
    "endividado": (_perfil_endividado, "Duas compras parceladas comendo o limite, sem nenhuma compra por impulso (impulso e cruzamento ficam bloqueados)."),
    "iniciante": (_perfil_iniciante, "Só 2 compras, sem limite definido: mostra os cartões vazios/bloqueados do painel."),
}


def montar_doc(perfil_nome, hoje=None):
    hoje = hoje or datetime.date.today()
    construtor, _ = PERFIS[perfil_nome]
    return construtor(hoje)


def main():
    parser = argparse.ArgumentParser(description="Cria ou remove contas fictícias pra testar o painel.")
    parser.add_argument("nome", nargs="?", help="nome da conta fictícia (ex: marina)")
    parser.add_argument("perfil", nargs="?", choices=list(PERFIS), help="perfil de dado a usar")
    parser.add_argument("--remover", action="store_true", help="remove a conta do banco em vez de criar")
    parser.add_argument("--listar", action="store_true", help="lista os perfis disponíveis e sai")
    args = parser.parse_args()

    if args.listar or not args.nome:
        print("Perfis disponíveis:\n")
        for nome_perfil, (_, descricao) in PERFIS.items():
            print(f"  {nome_perfil}: {descricao}")
        print("\nUso: .venv/bin/python3 criar_dados_demo.py <nome> <perfil>")
        print("     .venv/bin/python3 criar_dados_demo.py <nome> --remover")
        return

    if args.remover:
        with mem._conn().cursor() as cur:
            cur.execute("DELETE FROM mensagens WHERE usuario_id = %s", (args.nome,))
            cur.execute("DELETE FROM memoria WHERE usuario_id = %s", (args.nome,))
        print(f"conta '{args.nome}' removida do banco")
        return

    if not args.perfil:
        print("Falta o perfil. Rode com --listar pra ver as opções.")
        sys.exit(1)

    doc = montar_doc(args.perfil)
    mem.salvar_memoria(args.nome, doc)
    print(f"conta '{args.nome}' criada com o perfil '{args.perfil}' ({len(doc['compras'])} compras)")
    print(f"pra abrir: entra em http://localhost:8502 com o nome '{args.nome}'")


if __name__ == "__main__":
    main()
