"""Memoria persistente do Guardiao.

Guarda, por usuario, um unico documento JSON com o perfil, as necessidades,
os desejos, as compras e as analises. Esse documento e o cerebro duravel: e
o que faz o Guardiao lembrar da pessoa entre um uso e outro.

Tambem guarda as mensagens da conversa, mas a tela abre limpa a cada uso
(sessao nova). O historico antigo nao volta a aparecer para o usuario; a
continuidade vem da memoria, nao do rolo de mensagens.

Fonte da verdade: um arquivo SQLite local (guardiao.db) na raiz do projeto.
Sem servidor, sem nuvem. E o suficiente para validar a hipotese: a pessoa
volta e o Guardiao lembra dela.
"""

import datetime
import json
import sqlite3
from pathlib import Path

# O banco fica na raiz do projeto, ao lado do app.py.
CAMINHO_DB = Path(__file__).resolve().parent.parent / "guardiao.db"


def _memoria_vazia():
    """Estrutura inicial da memoria de um usuario novo."""
    return {
        "perfil": {"nome": None, "prioridade": None, "guardrails": []},
        "necessidades": [],  # itens que resolvem um problema concreto
        "desejos": [],       # itens ligados a vontade, sem problema concreto
        "compras": [],       # o que a pessoa ja comprou (para detectar duplicata)
        "analises": [],      # historico de vereditos dados
    }


def iniciar_banco():
    """Cria as tabelas se ainda nao existirem. Idempotente."""
    con = sqlite3.connect(CAMINHO_DB)
    con.execute(
        "CREATE TABLE IF NOT EXISTS memoria ("
        " usuario_id TEXT PRIMARY KEY,"
        " doc TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS mensagens ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " usuario_id TEXT NOT NULL,"
        " papel TEXT NOT NULL,"
        " conteudo TEXT NOT NULL)"
    )
    # Migracao leve: garante a coluna de data (para o teto de uso por dia).
    colunas = [linha[1] for linha in con.execute("PRAGMA table_info(mensagens)").fetchall()]
    if "criado_em" not in colunas:
        con.execute("ALTER TABLE mensagens ADD COLUMN criado_em TEXT")
    con.commit()
    con.close()


def ler_memoria(usuario_id):
    """Devolve o documento de memoria do usuario como dicionario."""
    con = sqlite3.connect(CAMINHO_DB)
    linha = con.execute(
        "SELECT doc FROM memoria WHERE usuario_id = ?", (usuario_id,)
    ).fetchone()
    con.close()
    if linha is None:
        return _memoria_vazia()
    try:
        return json.loads(linha[0])
    except json.JSONDecodeError:
        return _memoria_vazia()


def salvar_memoria(usuario_id, doc):
    """Grava (ou substitui) o documento de memoria do usuario."""
    con = sqlite3.connect(CAMINHO_DB)
    con.execute(
        "INSERT INTO memoria (usuario_id, doc) VALUES (?, ?)"
        " ON CONFLICT(usuario_id) DO UPDATE SET doc = excluded.doc",
        (usuario_id, json.dumps(doc, ensure_ascii=False)),
    )
    con.commit()
    con.close()


def ler_mensagens(usuario_id, desde_id=0):
    """Mensagens da conversa, em ordem, como lista de {papel, conteudo}.

    desde_id > 0 traz apenas as mensagens desta sessao (id maior que o marco
    de quando a pessoa entrou). Assim a tela abre limpa a cada uso, mesmo com
    todo o historico ainda guardado no banco.
    """
    con = sqlite3.connect(CAMINHO_DB)
    linhas = con.execute(
        "SELECT papel, conteudo FROM mensagens"
        " WHERE usuario_id = ? AND id > ? ORDER BY id",
        (usuario_id, desde_id),
    ).fetchall()
    con.close()
    return [{"papel": p, "conteudo": c} for (p, c) in linhas]


def ultimo_id(usuario_id):
    """Maior id de mensagem ja gravado para a pessoa (0 se nao houver nenhum).

    Serve de marco de inicio de sessao: tudo antes disso fica escondido da tela.
    """
    con = sqlite3.connect(CAMINHO_DB)
    linha = con.execute(
        "SELECT MAX(id) FROM mensagens WHERE usuario_id = ?", (usuario_id,)
    ).fetchone()
    con.close()
    return linha[0] or 0


def salvar_mensagem(usuario_id, papel, conteudo):
    """Anexa uma mensagem (papel = 'user' ou 'assistant') ao historico."""
    con = sqlite3.connect(CAMINHO_DB)
    con.execute(
        "INSERT INTO mensagens (usuario_id, papel, conteudo, criado_em)"
        " VALUES (?, ?, ?, datetime('now'))",
        (usuario_id, papel, conteudo),
    )
    con.commit()
    con.close()


def registrar_decisao(usuario_id, resumo, decisao):
    """Registra a decisao que a pessoa realmente tomou (comprou, esperou,
    vai comparar) depois de ver o diagnostico. E a decisao dela, nao so o
    veredito que o Guardiao deu, e alimenta a deteccao de duplicata.
    """
    doc = ler_memoria(usuario_id)
    entrada = {
        "resumo": resumo,
        "decisao": decisao,
        "data": datetime.date.today().isoformat(),
    }
    chave = "compras" if decisao == "comprou" else "analises"
    doc.setdefault(chave, []).append(entrada)
    salvar_memoria(usuario_id, doc)


def contar_mensagens_usuario_hoje(usuario_id):
    """Quantas mensagens o usuario ja mandou hoje (para o teto de uso)."""
    con = sqlite3.connect(CAMINHO_DB)
    total = con.execute(
        "SELECT COUNT(*) FROM mensagens"
        " WHERE usuario_id = ? AND papel = 'user'"
        " AND date(criado_em) = date('now')",
        (usuario_id,),
    ).fetchone()[0]
    con.close()
    return total
