"""Memoria persistente do Guardiao.

Guarda, por usuario, um unico documento JSON com o perfil, as necessidades,
os desejos, as compras e as analises. Esse documento e o cerebro duravel: e
o que faz o Guardiao lembrar da pessoa entre um uso e outro.

Tambem guarda as mensagens da conversa, mas a tela abre limpa a cada uso
(sessao nova). O historico antigo nao volta a aparecer para o usuario; a
continuidade vem da memoria, nao do rolo de mensagens.

Fonte da verdade: banco Postgres no Supabase (DATABASE_URL no .env). Antes
disso era um arquivo SQLite local, que sumia toda vez que o app no Streamlit
Cloud hibernava. Migrado pra nao perder a memoria de ninguem em producao.
"""

import datetime
import os
from pathlib import Path

import psycopg2
import psycopg2.extras


def _carregar_url_do_env():
    """Le DATABASE_URL do ambiente ou, se nao estiver setada (dev local sem
    exportar variavel), sobe os diretorios procurando um .env com a chave.
    Mesmo padrao ja usado no projeto pra outros segredos.
    """
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    cur = Path(__file__).resolve().parent
    while cur.parent != cur:
        candidato = cur / ".env"
        if candidato.exists():
            for linha in candidato.read_text(encoding="utf-8").splitlines():
                if linha.startswith("DATABASE_URL="):
                    return linha.split("=", 1)[1].strip().strip('"').strip("'")
        cur = cur.parent
    raise RuntimeError(
        "DATABASE_URL nao encontrada no .env. Pegue a connection string no "
        "painel do Supabase (Project Settings > Database > Connection string) "
        "e salve em DATABASE_URL no .env."
    )


_URL_BANCO = os.environ.get("DATABASE_URL") or _carregar_url_do_env()

# Uma unica conexao reusada pelo processo inteiro (o app roda como um servidor
# Python de vida longa, nao faz sentido abrir conexao nova a cada chamada como
# fazia o SQLite local). Reconecta sozinha se a conexao cair.
_conexao = None


def _conn():
    global _conexao
    if _conexao is None or _conexao.closed:
        _conexao = psycopg2.connect(_URL_BANCO)
        _conexao.autocommit = True
    return _conexao


def _memoria_vazia():
    """Estrutura inicial da memoria de um usuario novo."""
    return {
        "perfil": {"nome": None, "prioridade": None, "guardrails": []},
        "necessidades": [],  # itens que resolvem um problema concreto
        "desejos": [],       # itens ligados a vontade, sem problema concreto
        "compras": [],       # o que a pessoa ja comprou (para detectar duplicata)
        "analises": [],      # historico de vereditos dados
        "lista_mercado": [],  # itens do dia a dia que a pessoa pediu pra anotar
        "precos": [],        # historico de precos PAGOS: {item, preco, local, data}
    }


def iniciar_banco():
    """Cria as tabelas se ainda nao existirem. Idempotente."""
    with _conn().cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS memoria ("
            " usuario_id TEXT PRIMARY KEY,"
            " doc JSONB NOT NULL)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS mensagens ("
            " id BIGSERIAL PRIMARY KEY,"
            " usuario_id TEXT NOT NULL,"
            " papel TEXT NOT NULL,"
            " conteudo TEXT NOT NULL,"
            " criado_em TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_mensagens_usuario"
            " ON mensagens (usuario_id, id)"
        )


def ler_memoria(usuario_id):
    """Devolve o documento de memoria do usuario como dicionario."""
    with _conn().cursor() as cur:
        cur.execute("SELECT doc FROM memoria WHERE usuario_id = %s", (usuario_id,))
        linha = cur.fetchone()
    if linha is None:
        return _memoria_vazia()
    return linha[0]  # psycopg2 ja devolve JSONB como dict


def salvar_memoria(usuario_id, doc):
    """Grava (ou substitui) o documento de memoria do usuario."""
    with _conn().cursor() as cur:
        cur.execute(
            "INSERT INTO memoria (usuario_id, doc) VALUES (%s, %s)"
            " ON CONFLICT (usuario_id) DO UPDATE SET doc = EXCLUDED.doc",
            (usuario_id, psycopg2.extras.Json(doc)),
        )


def ler_mensagens(usuario_id, desde_id=0):
    """Mensagens da conversa, em ordem, como lista de {papel, conteudo}.

    desde_id > 0 traz apenas as mensagens desta sessao (id maior que o marco
    de quando a pessoa entrou). Assim a tela abre limpa a cada uso, mesmo com
    todo o historico ainda guardado no banco.
    """
    with _conn().cursor() as cur:
        cur.execute(
            "SELECT papel, conteudo FROM mensagens"
            " WHERE usuario_id = %s AND id > %s ORDER BY id",
            (usuario_id, desde_id),
        )
        linhas = cur.fetchall()
    return [{"papel": p, "conteudo": c} for (p, c) in linhas]


def ultimo_id(usuario_id):
    """Maior id de mensagem ja gravado para a pessoa (0 se nao houver nenhum).

    Serve de marco de inicio de sessao: tudo antes disso fica escondido da tela.
    """
    with _conn().cursor() as cur:
        cur.execute("SELECT MAX(id) FROM mensagens WHERE usuario_id = %s", (usuario_id,))
        linha = cur.fetchone()
    return linha[0] or 0


def salvar_mensagem(usuario_id, papel, conteudo):
    """Anexa uma mensagem (papel = 'user' ou 'assistant') ao historico."""
    with _conn().cursor() as cur:
        cur.execute(
            "INSERT INTO mensagens (usuario_id, papel, conteudo, criado_em)"
            " VALUES (%s, %s, %s, now())",
            (usuario_id, papel, conteudo),
        )


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
    """Quantas mensagens o usuario ja mandou hoje (para o teto de uso).

    Compara em UTC, mesmo criterio que o SQLite local usava (date('now')).
    """
    with _conn().cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM mensagens"
            " WHERE usuario_id = %s AND papel = 'user'"
            " AND (criado_em AT TIME ZONE 'UTC')::date = (now() AT TIME ZONE 'UTC')::date",
            (usuario_id,),
        )
        total = cur.fetchone()[0]
    return total
