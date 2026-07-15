"""Guardiao. App de chat que ajuda a tomar melhores decisoes de compra.

Roda com: streamlit run app.py
Precisa de ANTHROPIC_API_KEY no arquivo .env (ou no ambiente).
"""

import base64
import datetime
import html
import itertools
import os
import re
import unicodedata
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from streamlit_mic_recorder import speech_to_text

from guardiao import cerebro
from guardiao import memoria as mem
from guardiao import painel

CAMINHO_ASSETS = Path(__file__).resolve().parent / "assets"

# Paleta oficial da marca (Design System Guardião do Bolso by IAgilize),
# na linha "escura e tech" escolhida pela fundadora: fundo quase preto,
# cartões em vidro fosco (glassmorphism) flutuando por cima.
COR_NAVY = "#0C1D2E"
COR_LARANJA = "#FF8A00"
COR_OFFWHITE = "#F7F7F2"
COR_TEXTO_CLARO = "#F2F3F5"
COR_VERDE = "#2BA745"
COR_AMARELO = "#F5A623"
COR_VERMELHO = "#EF4444"
COR_AZUL_INFO = "#2F6DF6"

# Vidro fosco (glassmorphism): fundo semitransparente + blur, usado nos
# cartões de diagnostico e no aviso de alerta, flutuando sobre o fundo escuro.
VIDRO_BG = "rgba(255,255,255,0.06)"
VIDRO_BORDA = "rgba(255,255,255,0.14)"


def _injetar_estilo_global():
    """Fundo escuro com brilho sutil de gradiente (laranja + azul da marca),
    dando a sensacao 'tech' pedida pela fundadora. Roda uma vez por tela.
    """
    st.markdown(
        '<style>[data-testid="stAppViewContainer"], [data-testid="stMain"] {'
        f'background-color: {COR_NAVY};'
        "background-image:"
        f"radial-gradient(circle at 12% 18%, {COR_LARANJA}1A 0%, transparent 45%),"
        f"radial-gradient(circle at 88% 82%, {COR_AZUL_INFO}22 0%, transparent 45%);"
        "background-attachment: fixed;"
        "}</style>",
        unsafe_allow_html=True,
    )

# Marca do produto: o simbolo (tijolinhos) da IAgilize, mais o lockup
# "Guardião do Bolso" / "by IAgilize" com o tracinho laranja de assinatura.
# Usa a versao negativa (blocos brancos, bloco laranja preservado), pois o
# fundo do app e escuro (COR_NAVY) e a versao navy original ficava sem
# contraste. Recorte gerado a partir de icone.png trocando so os pixels navy
# por off-white, preservando alpha e o bloco laranja (Design System, secao
# "Logo para fundo escuro / versao negativa", fundo azul-marinho recomendado).
CAMINHO_ICONE_NEGATIVO = CAMINHO_ASSETS / "icone-negativo.png"
_ICONE_B64 = base64.b64encode(CAMINHO_ICONE_NEGATIVO.read_bytes()).decode("ascii")

# Avatares do chat: o Streamlit usa uma "carinha" e um "robozinho" genericos
# por padrao quando nenhum avatar e definido. Trocados por:
# - Guardiao: circulo navy com o quadradinho laranja da marca no centro
#   (elemento "ponto de decisao" do design system: o checkpoint antes da
#   compra). Gerado por codigo em assets/avatar-guardiao.png, quadrado
#   perfeito, sem a distorcao que o lockup retangular sofria no circulo.
# - Pessoa: circulo discreto com a inicial do nome dela, gerado em tempo de
#   execucao (cada pessoa ve a propria letra).
AVATAR_ASSISTENTE = str(CAMINHO_ASSETS / "avatar-guardiao.png")

_CACHE_AVATAR_USUARIO = {}


def _avatar_usuario(usuario_id):
    """Circulo cinza-azulado com a inicial do nome da pessoa, na paleta da
    marca. Gerado uma vez por nome e guardado em cache na memoria do processo.
    Retorna uma imagem PIL (aceita direto por st.chat_message).
    """
    inicial = (usuario_id or "?").strip()[:1].upper() or "?"
    if inicial in _CACHE_AVATAR_USUARIO:
        return _CACHE_AVATAR_USUARIO[inicial]

    from PIL import Image, ImageDraw, ImageFont

    S = 512  # desenha grande e reduz, pra borda e letra sairem suaves
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, S - 4, S - 4], fill=(42, 53, 80, 255), outline=(255, 255, 255, 46), width=6)

    # fonte em negrito: tenta as do sistema (Mac local, Linux no deploy) e,
    # em ultimo caso, usa a padrao do PIL
    fonte = None
    for caminho in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            fonte = ImageFont.truetype(caminho, int(S * 0.5))
            break
        except OSError:
            continue
    if fonte is None:
        fonte = ImageFont.load_default(size=int(S * 0.5))

    caixa = d.textbbox((0, 0), inicial, font=fonte)
    lw, lh = caixa[2] - caixa[0], caixa[3] - caixa[1]
    d.text(((S - lw) / 2 - caixa[0], (S - lh) / 2 - caixa[1]), inicial, font=fonte, fill=(247, 247, 242, 255))

    img = img.resize((128, 128), Image.LANCZOS)
    _CACHE_AVATAR_USUARIO[inicial] = img
    return img


def _logo_html(altura_px, centralizado=False):
    """Simbolo + lockup 'Guardião do Bolso' / 'by IAgilize'. altura_px e a
    altura do simbolo; o texto acompanha proporcionalmente. centralizado=True
    alinha ao centro (tela de abertura).
    """
    fonte_titulo = round(altura_px * 0.6)
    fonte_sub = round(altura_px * 0.24)
    justify = "center" if centralizado else "flex-start"
    align = "center" if centralizado else "flex-start"
    return (
        f'<div style="display:flex; align-items:center; gap:12px; '
        f'justify-content:{justify}; margin-bottom:12px;">'
        f'<img src="data:image/png;base64,{_ICONE_B64}" style="height:{altura_px}px; width:auto;" />'
        f'<div style="display:flex; flex-direction:column; align-items:{align};">'
        f'<span style="font-size:{fonte_titulo}px; font-weight:700; color:{COR_TEXTO_CLARO}; '
        f'line-height:1.05; letter-spacing:-0.5px;">Guardião do Bolso</span>'
        f'<span style="font-size:{fonte_sub}px; font-weight:600; color:{COR_LARANJA}; '
        f'text-transform:uppercase; letter-spacing:1px; margin-top:2px;">by IAgilize</span>'
        f'<div style="width:36px; height:3px; background:{COR_LARANJA}; margin-top:5px; '
        f'border-radius:2px;"></div>'
        f"</div></div>"
    )


def _cabecalho_logo():
    """Cabecalho padrao das telas: o simbolo + o lockup 'Guardião do Bolso'."""
    st.markdown(_logo_html(38), unsafe_allow_html=True)

# Os 5 blocos foram recortados pixel a pixel do logo real da IAgilize
# (assets/logoGuardiaoBolso.png), preservando fidelidade total a marca.
# Cada bbox e (x0, y0, x1, y1) em coordenadas absolutas do arquivo original.
# Ordem de aparecimento definida pela fundadora: 4, 5, 3, 2, 1.
_BLOCOS_ICONE = {
    1: (175, 259, 200, 287),  # quadrado laranja, topo direita
    2: (152, 272, 200, 311),  # bloco em L, navy
    3: (106, 287, 146, 311),  # retangulo do meio, navy
    4: (106, 316, 129, 341),  # quadrado de baixo a esquerda, navy
    5: (135, 316, 200, 341),  # barra larga de baixo, navy
}
# De baixo pra cima e da direita pra esquerda, exceto o quadrado laranja
# (numero 1), que aparece por ultimo sempre, no topo.
_ORDEM_APARECIMENTO = [5, 4, 2, 3, 1]
_FRAME_X0 = min(b[0] for b in _BLOCOS_ICONE.values())
_FRAME_Y0 = min(b[1] for b in _BLOCOS_ICONE.values())
_FRAME_X1 = max(b[2] for b in _BLOCOS_ICONE.values())
_FRAME_Y1 = max(b[3] for b in _BLOCOS_ICONE.values())


def _icone_iagilize_animado():
    """Monta o HTML do icone da IAgilize (os tijolinhos da marca) surgindo em
    sequencia, um bloco de cada vez, na ordem definida pela fundadora. Usa os
    recortes reais do logo (assets/bloco_N.png), nao um redesenho, pra manter
    fidelidade total a marca ja usada no marketing.
    """
    escala = 2.4
    largura = (_FRAME_X1 - _FRAME_X0 + 1) * escala
    altura = (_FRAME_Y1 - _FRAME_Y0 + 1) * escala

    camadas = []
    for ordem, num in enumerate(_ORDEM_APARECIMENTO):
        x0, y0, x1, y1 = _BLOCOS_ICONE[num]
        b64 = base64.b64encode((CAMINHO_ASSETS / f"bloco_{num}.png").read_bytes()).decode("ascii")
        left = (x0 - _FRAME_X0) * escala
        top = (y0 - _FRAME_Y0) * escala
        largura_bloco = (x1 - x0 + 1) * escala
        altura_bloco = (y1 - y0 + 1) * escala
        atraso = 0.1 + ordem * 0.4
        camadas.append(
            f'<img src="data:image/png;base64,{b64}" '
            f'style="position:absolute; left:{left}px; top:{top}px; '
            f'width:{largura_bloco}px; height:{altura_bloco}px; '
            f'opacity:0; animation: guardiao-surgir 0.5s ease-out {atraso}s forwards;" />'
        )

    # Tudo em uma linha so, sem indentacao: o Markdown do Streamlit trata 4+
    # espacos de recuo como bloco de codigo, o que quebrava esse HTML antes.
    estilo = (
        "<style>@keyframes guardiao-surgir {"
        "0% { opacity: 0; transform: translateY(6px) scale(0.9); } "
        "100% { opacity: 1; transform: translateY(0) scale(1); } }</style>"
    )
    return (
        f'<div style="position:relative; width:{largura}px; height:{altura}px; margin:0 auto;">'
        f'{"".join(camadas)}'
        f'</div>{estilo}'
    )

load_dotenv()  # carrega ANTHROPIC_API_KEY e GUARDIAO_MODELO do .env, se existir
mem.iniciar_banco()

st.set_page_config(
    page_title="Guardião",
    page_icon=str(CAMINHO_ASSETS / "icone.png"),
    layout="centered",
)
_injetar_estilo_global()

# Teto de uso por dia (controla o custo por pessoa). Ajustavel no .env.
LIMITE_DIA = int(os.environ.get("LIMITE_MENSAGENS_DIA", "50"))

# Modelos disponiveis para trocar na hora (equilibrio vs preco).
MODELOS = {
    "Sonnet (equilibrado)": "claude-sonnet-5",
    "Haiku (mais barato)": "claude-haiku-4-5",
}

# Perfil rapido (onboarding objetivo, no primeiro uso). Opcoes prontas pra
# pessoa clicar, em vez de campo aberto que trava quem nao e organizado.
OPCAO_OBJETIVO = "Juntar dinheiro pra um objetivo"
OPCOES_PRIORIDADE = [
    "Não entrar em dívida",
    "Parar de comprar por impulso",
    OPCAO_OBJETIVO,
    "Cortar gastos que não valem a pena",
    "Organizar minhas finanças",
]
OPCOES_GUARDRAILS = [
    "Tô pagando um cartão ou dívida",
    "Tenho um limite de quanto posso gastar por mês",
    "Momento sem renda, preciso segurar tudo",
    "Nada disso agora",
]


ROTULOS_CONSCIENCIA = [
    "Motivação da compra",
    "Clareza",
    "Comparação",
    "Checagem de segurança",
    "Viabilidade financeira",
]
_ALTERNATIVAS_ROTULOS = "|".join(ROTULOS_CONSCIENCIA)

# Acha os rotulos em qualquer formatacao (uma linha por rotulo ou tudo junto)
# e devolve o que vem antes, o conteudo de cada rotulo e o que vem depois.
# Motivação, Clareza e Viabilidade financeira sempre aparecem; Comparação e
# Checagem de seguranca sao condicionais (so quando o modelo os escreve).
# Isso evita que o texto vire um paragrafo so quando o modelo nao separa as
# linhas com espaco em branco (comportamento normal do Markdown).
_PADRAO_ROTULOS = re.compile(
    rf"({_ALTERNATIVAS_ROTULOS})\s*:\s*(.*?)"
    rf"(?=(?:{_ALTERNATIVAS_ROTULOS})\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)


_QUEBRA_PARAGRAFO = re.compile(r"\n\s*\n")
_FIM_DE_FRASE = re.compile(r"(.*?[.!?])\s+(.*)", re.DOTALL)


def _extrair_rotulos(texto):
    encontrados = list(_PADRAO_ROTULOS.finditer(texto))
    if len(encontrados) < 3:
        return None
    rotulos = {}
    fim = ""
    ultimo = len(encontrados) - 1
    for i, m in enumerate(encontrados):
        valor = m.group(2).strip()
        if i == ultimo:
            # O ultimo rotulo pode vir colado com a frase de acao final. Corta
            # primeiro numa linha em branco (se existir) e, sem isso, na
            # primeira pontuacao de fim de frase: cada rotulo e no maximo uma
            # frase curta, entao o que sobra depois e a frase de acao.
            partes = _QUEBRA_PARAGRAFO.split(valor, maxsplit=1)
            if len(partes) == 2:
                valor, fim = partes[0].strip(), partes[1].strip()
            else:
                corte = _FIM_DE_FRASE.match(valor)
                if corte:
                    valor, fim = corte.group(1).strip(), corte.group(2).strip()
        rotulos[m.group(1)] = valor
    inicio = texto[: encontrados[0].start()].strip()
    return inicio, rotulos, fim


def _ultima_fala_do_usuario(historico):
    """Acha a ultima mensagem da pessoa, para resumir a decisao registrada."""
    for m in reversed(historico):
        if m["papel"] == "user":
            return m["conteudo"]
    return ""


def mostrar_resposta(texto):
    """Mostra a resposta do Guardião.

    Se em algum ponto ela trouxer o aviso 'Não fecha ainda' (nao precisa ser a
    primeira linha, pode vir depois de uma saudacao ou pergunta), destaca em
    amarelo. Os tres rotulos da Consciencia de Compra (Motivação, Clareza,
    Viabilidade) sempre aparecem como tres cartoes separados, nunca como um
    paragrafo so.
    """
    linhas = texto.split("\n")
    indice_aviso = next(
        (i for i, linha in enumerate(linhas) if linha.strip().startswith("⚠️")), None
    )

    if indice_aviso is not None:
        antes = "\n".join(linhas[:indice_aviso]).strip()
        aviso = linhas[indice_aviso].strip().lstrip("⚠️").strip() or "Não fecha ainda"
        if antes:
            st.markdown(antes)
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:10px; '
            f'background:{COR_VERMELHO}22; backdrop-filter:blur(16px); '
            f'-webkit-backdrop-filter:blur(16px); border:1px solid {COR_VERMELHO}55; '
            f'border-radius:14px; padding:12px 16px; margin:8px 0;">'
            f'<span style="font-size:18px;">⚠️</span>'
            f'<strong style="color:#FFD5D5; font-size:15px;">{html.escape(aviso)}</strong>'
            f"</div>",
            unsafe_allow_html=True,
        )
        corpo = "\n".join(linhas[indice_aviso + 1 :]).strip()
    else:
        corpo = texto

    extraido = _extrair_rotulos(corpo)
    if extraido is None:
        st.markdown(corpo)
        return

    inicio, rotulos, fim = extraido
    if inicio:
        st.markdown(inicio)
    for rotulo in ROTULOS_CONSCIENCIA:
        valor = rotulos.get(rotulo)
        if not valor:
            continue
        st.markdown(
            f'<div style="background:{VIDRO_BG}; backdrop-filter:blur(16px); '
            f'-webkit-backdrop-filter:blur(16px); border:1px solid {VIDRO_BORDA}; '
            f'border-radius:16px; padding:14px 18px; margin:10px 0; '
            f'box-shadow:0 8px 24px rgba(0,0,0,0.25);">'
            f'<div style="color:{COR_LARANJA}; font-weight:700; font-size:12px; '
            f'text-transform:uppercase; letter-spacing:0.6px; margin-bottom:4px;">'
            f"{html.escape(rotulo)}</div>"
            f'<div style="color:{COR_TEXTO_CLARO}; font-size:15px; line-height:1.45;">'
            f"{html.escape(valor)}</div></div>",
            unsafe_allow_html=True,
        )
    if fim:
        st.markdown(fim)


def _estilizar_microfone(chave_widget):
    """Reposiciona o microfone (streamlit_mic_recorder) para dentro da propria
    barra de escrita, colado a esquerda do botao de enviar (efeito "ChatGPT"),
    sem fundo nem borda propria. Reusado nas duas telas (boas-vindas e chat).
    """
    components.html(
        f"""
        <script>
        (function () {{
            const doc = window.parent.document;
            const janela = window.parent;
            function ajustar() {{
                const enviar = doc.querySelector('button[data-testid="stChatInputSubmitButton"]');
                const micWrap = doc.querySelector('.st-key-{chave_widget}');
                if (!enviar || !micWrap) return;
                const r = enviar.getBoundingClientRect();
                const tamanho = 32;
                const espaco = 4;
                micWrap.style.position = 'fixed';
                micWrap.style.zIndex = '1000000';
                micWrap.style.width = tamanho + 'px';
                micWrap.style.minWidth = tamanho + 'px';
                micWrap.style.height = tamanho + 'px';
                micWrap.style.bottom = (janela.innerHeight - r.bottom) + 'px';
                micWrap.style.right = (janela.innerWidth - r.left + espaco) + 'px';
                micWrap.style.left = 'auto';
                micWrap.style.top = 'auto';
                micWrap.style.background = 'transparent';
                micWrap.style.boxShadow = 'none';
                const iframe = micWrap.querySelector('iframe');
                if (!iframe) return;
                iframe.style.width = tamanho + 'px';
                iframe.style.height = tamanho + 'px';
                iframe.style.background = 'transparent';
                try {{
                    const idoc = iframe.contentDocument;
                    if (idoc && !idoc.getElementById('guardiao-mic-style')) {{
                        const style = idoc.createElement('style');
                        style.id = 'guardiao-mic-style';
                        style.textContent = `
                            html, body {{ background: transparent !important; margin: 0; }}
                            .myButton {{
                                background: transparent !important;
                                border: none !important;
                                box-shadow: none !important;
                                width: 32px !important;
                                height: 32px !important;
                                font-size: 18px !important;
                                padding: 0 !important;
                            }}
                        `;
                        idoc.head.appendChild(style);
                    }}
                }} catch (e) {{
                    /* silencioso: se o iframe nao permitir acesso, mantem o estilo padrao */
                }}
            }}
            ajustar();
            new MutationObserver(ajustar).observe(doc.body, {{childList: true, subtree: true}});
            window.addEventListener('resize', ajustar);
            setInterval(ajustar, 400);
        }})();
        </script>
        """,
        height=0,
    )


def _autofoco(seletor):
    """Coloca o cursor no campo mais provavel assim que a tela abre, sem
    roubar o foco se a pessoa ja estiver com outra coisa selecionada.
    """
    components.html(
        f"""
        <script>
        (function () {{
            const doc = window.parent.document;
            function focar() {{
                const el = doc.querySelector('{seletor}');
                if (!el) return;
                const ativo = doc.activeElement;
                const nadaFocado = !ativo || ativo === doc.body;
                if (nadaFocado) el.focus();
            }}
            setTimeout(focar, 150);
        }})();
        </script>
        """,
        height=0,
    )


# Lista de mercado: operacao de armazenamento puro, 100% em codigo. Qualquer
# mensagem que mencione "lista" e tratada aqui, sem passar pelo modelo: sem
# custo, sem follow-up de pendencias, sem mistura com o fluxo de decisao de
# compra. Incluir, tirar, limpar e mostrar sao operacoes de banco.
_RE_ADICIONAR_LISTA = re.compile(
    r"\b(anota|anote|poe|põe|bota|bote|adiciona|adicione|coloca|coloque|inclui|inclua|acrescenta|acrescente)\b"
)
_RE_REMOVER_LISTA = re.compile(
    r"\b(tira|tire|remove|remova|risca|risque|apaga|apague|exclui|exclua|comprei)\b"
)
_RE_LIMPAR_LISTA = re.compile(r"\b(limpa|limpe|zera|zere|esvazia|esvazie)\b|comprei tudo")

# Pedacos que nao sao item: o proprio comando, a referencia a lista e muletas
# de fala ("ai", "pra mim", "por favor"). Removidos antes de extrair os itens.
_RE_RUIDO_LISTA = re.compile(
    r"\b(anota|anote|poe|põe|bota|bote|adiciona|adicione|coloca|coloque|inclui|inclua"
    r"|acrescenta|acrescente|tira|tire|remove|remova|risca|risque|apaga|apague|exclui|exclua"
    r"|comprei|ja|já|na|da|a|o|minha|lista|de|do|mercado|compras|ai|aí|la|lá"
    r"|pra|para|mim|por|favor|também|tambem|e?nt[aã]o)\b"
)


def _sem_acento(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def _extrair_itens_lista(texto):
    """Extrai os itens de uma frase de lista: tira o comando e as muletas,
    depois separa por virgula e "e". Ex: "anota arroz, feijão e sabão em pó
    na lista" vira ["arroz", "feijão", "sabão em pó"].
    """
    limpo = texto.replace(":", " ").replace(";", ",")
    partes = re.split(r",| e ", limpo)
    itens = []
    for parte in partes:
        parte = _RE_RUIDO_LISTA.sub(" ", parte)
        parte = re.sub(r"\s+", " ", parte).strip(" .!?")
        if parte:
            itens.append(parte)
    return itens


def _resposta_lista_mercado(usuario_id, entrada):
    """Trata QUALQUER pedido de lista de mercado direto no banco, sem modelo.
    Devolve o texto da resposta, ou None quando a mensagem nao e sobre a lista
    (ai segue o fluxo normal de decisao de compra pelo modelo).
    """
    texto = entrada.lower().strip()
    if "lista" not in texto:
        return None

    doc = mem.ler_memoria(usuario_id)
    lista = doc.setdefault("lista_mercado", [])

    # Limpar vem antes de remover: "limpa a lista" nao pode cair no remover.
    if _RE_LIMPAR_LISTA.search(texto):
        lista.clear()
        mem.salvar_memoria(usuario_id, doc)
        return "Lista de mercado esvaziada."

    if _RE_ADICIONAR_LISTA.search(texto):
        itens = _extrair_itens_lista(texto)
        if not itens:
            return "Não entendi quais itens anotar. Fala assim: anota arroz e feijão na lista."
        # Item descrito com muitos detalhes nao e mercado, e bem duravel
        # (eletrodomestico, eletronico) falado por extenso. Nao adiciona:
        # devolve None e deixa cair no fluxo normal (modelo faz o diagnostico
        # de compra de verdade, com rotulos).
        if any(cerebro._parece_bem_duravel(i) for i in itens):
            return None
        ja_tinha = {_sem_acento(i.lower()) for i in lista}
        novos, repetidos = [], []
        for item in itens:
            chave = _sem_acento(item.lower())
            if chave in ja_tinha:
                repetidos.append(item)
            else:
                lista.append(item)
                ja_tinha.add(chave)
                novos.append(item)
        mem.salvar_memoria(usuario_id, doc)
        resposta = ""
        if novos:
            resposta = f"Anotado: {', '.join(novos)}. Na lista: {len(lista)} " + (
                "item." if len(lista) == 1 else "itens."
            )
        if repetidos:
            resposta = (resposta + " " if resposta else "") + f"Já estava na lista: {', '.join(repetidos)}."
        return resposta

    if _RE_REMOVER_LISTA.search(texto):
        itens = _extrair_itens_lista(texto)
        if not itens:
            return "Não entendi o que tirar. Fala assim: tira o arroz da lista."
        tirados, nao_achados = [], []
        for item in itens:
            chave = _sem_acento(item.lower())
            achou = None
            for salvo in lista:
                chave_salvo = _sem_acento(salvo.lower())
                if chave == chave_salvo or chave in chave_salvo or chave_salvo in chave:
                    achou = salvo
                    break
            if achou:
                lista.remove(achou)
                tirados.append(achou)
            else:
                nao_achados.append(item)
        mem.salvar_memoria(usuario_id, doc)
        resposta = ""
        if tirados:
            fica = ", ".join(lista) if lista else "nada, lista vazia"
            resposta = f"Tirei: {', '.join(tirados)}. Fica: {fica}."
        if nao_achados:
            resposta = (resposta + " " if resposta else "") + f"Não achei na lista: {', '.join(nao_achados)}."
        return resposta

    # Sem verbo de mudanca: e leitura ("me manda a lista", "o que tem na lista?").
    if not lista:
        return "Sua lista de mercado está vazia."
    return "\n".join(f"- {item}" for item in lista)


def _processar_entrada(usuario_id, entrada, desde_id):
    """Fluxo comum das duas telas ao receber uma mensagem: tenta o atalho da
    lista de mercado (sem custo, nao conta no teto diario) e, se nao for isso,
    segue pro modelo respeitando o teto de uso.
    """
    atalho = _resposta_lista_mercado(usuario_id, entrada)
    if atalho is not None:
        mem.salvar_mensagem(usuario_id, "user", entrada)
        mem.salvar_mensagem(usuario_id, "assistant", atalho)
        st.rerun()
    if mem.contar_mensagens_usuario_hoje(usuario_id) >= LIMITE_DIA:
        st.warning(
            "Você já conversou bastante comigo hoje. Volta amanhã que eu te espero, "
            "com tudo que já lembro de você guardado."
        )
        return
    mem.salvar_mensagem(usuario_id, "user", entrada)
    with st.spinner("pensando..."):
        modelo = st.session_state.get("modelo", cerebro.MODELO)
        resposta = cerebro.responder(usuario_id, modelo, desde_id)
    mem.salvar_mensagem(usuario_id, "assistant", resposta)
    st.rerun()


def tela_de_entrada():
    """Pede um nome para identificar a pessoa e manter a memoria entre sessoes."""
    _cabecalho_logo()
    st.caption("Fala comigo antes de comprar. Eu lembro de você.")
    nome = st.text_input("Como você se chama?", placeholder="seu nome ou apelido")
    _autofoco('input[aria-label="Como você se chama?"]')
    if st.button("Entrar", type="primary") and nome.strip():
        st.session_state.usuario_id = nome.strip().lower()
        st.session_state.nome = nome.strip()
        # Marco de inicio de sessao: a tela abre limpa, sem o rolo de conversas
        # antigas. A memoria por tras continua guardada e entra na conversa nova.
        st.session_state.sessao_desde_id = mem.ultimo_id(st.session_state.usuario_id)
        # Guarda o nome na URL: assim um reload ou uma nova visita no mesmo
        # navegador reconhece a pessoa sem perguntar o nome de novo.
        st.query_params["usuario"] = nome.strip()
        st.rerun()


def barra_lateral(usuario_id):
    """Memoria (so leitura) + seletor de modelo para testes."""
    memoria = mem.ler_memoria(usuario_id)
    with st.sidebar:
        if st.button("📊 Meu painel", use_container_width=True):
            st.session_state.tela = "painel"
            st.rerun()
        st.divider()

        # Reiniciar analise: limpa a tela e comeca do zero, mantendo tudo que
        # o Guardiao ja lembra da pessoa (a memoria por tras nao e apagada).
        if st.button("🔄 Reiniciar análise", use_container_width=True):
            st.session_state.sessao_desde_id = mem.ultimo_id(usuario_id)
            st.rerun()
        st.divider()

        # Seletor de modelo: deixa comparar qualidade e custo ao vivo.
        nomes = list(MODELOS.keys())
        padrao = 0
        for i, chave in enumerate(MODELOS.values()):
            if chave == cerebro.MODELO:
                padrao = i
        escolha = st.selectbox("Modelo", nomes, index=padrao)
        st.session_state.modelo = MODELOS[escolha]

        usados = mem.contar_mensagens_usuario_hoje(usuario_id)
        st.caption(f"Uso hoje: {usados} de {LIMITE_DIA} mensagens")

        st.divider()
        st.subheader("O que eu lembro de você")
        perfil = memoria.get("perfil", {})
        if perfil.get("prioridade"):
            st.markdown("**Sua prioridade**")
            st.write(perfil["prioridade"])

        limite = perfil.get("limite_mensal")
        if limite:
            mes_atual = datetime.date.today().isoformat()[:7]  # "AAAA-MM"
            gasto_mes = sum(
                float(c.get("preco") or 0)
                for c in memoria.get("compras", [])
                if isinstance(c, dict) and str(c.get("data", "")).startswith(mes_atual)
            )
            st.markdown("**Limite mensal**")
            limite_fmt = f"R\\$ {limite:.2f}".replace(".", ",")
            gasto_fmt = f"R\\$ {gasto_mes:.2f}".replace(".", ",")
            st.write(f"{gasto_fmt} de {limite_fmt} gastos esse mês")
            st.progress(min(gasto_mes / limite, 1.0))

        for titulo, chave in [
            ("Necessidades abertas", "necessidades"),
            ("Desejos", "desejos"),
            ("Compras recentes", "compras"),
            ("Lista de mercado", "lista_mercado"),
        ]:
            itens = memoria.get(chave, [])
            if itens:
                st.markdown(f"**{titulo}**")
                for item in itens:
                    if isinstance(item, dict):
                        rotulo = item.get("item") or item.get("titulo") or item.get("nome") or str(item)
                        # Cotacoes coletadas durante a cacada de preco do item.
                        cotacoes = item.get("cotacoes") or []
                        if cotacoes:
                            # O cifrao precisa de escape: dois "$" na mesma linha
                            # fazem o Markdown do Streamlit virar formula matematica.
                            vistas = "; ".join(
                                f"R\\$ {c['preco']:.2f}".replace(".", ",")
                                + (f" ({c['local']})" if c.get("local") else "")
                                for c in cotacoes
                            )
                            rotulo = f"{rotulo} (cotações: {vistas})"
                    else:
                        rotulo = str(item)
                    st.write(f"- {rotulo}")

        # Precos de referencia: o ultimo preco PAGO de cada item, com local e data.
        precos = memoria.get("precos", [])
        if precos:
            ultimos = {}
            for p in precos:  # lista cronologica: o ultimo registro do item vence
                if isinstance(p, dict) and p.get("item"):
                    ultimos[str(p["item"]).lower()] = p
            st.markdown("**Preços de referência**")
            for p in ultimos.values():
                # .get() com fallback pro "valor": registro pode ter vindo de um
                # salvar_memoria antigo, escrito com formato diferente do esperado.
                preco_num = p.get("preco", p.get("valor", 0)) or 0
                try:
                    preco_num = float(preco_num)
                except (TypeError, ValueError):
                    preco_num = 0
                valor = f"R\\$ {preco_num:.2f}".replace(".", ",")
                onde = f", {p['local']}" if p.get("local") else ""
                quando = f"{p['data'][8:10]}/{p['data'][5:7]}" if p.get("data") else ""
                # Marca visualmente os itens de uso continuo (remedio, cosmetico
                # de reposicao), que sao os que disparam o atalho de recompra.
                selo = " 🔁" if p.get("uso_continuo") else ""
                st.write(f"- {p['item']}: {valor}{onde} ({quando}){selo}")
            if any(p.get("uso_continuo") for p in ultimos.values()):
                st.caption("🔁 = uso contínuo, reposição sem passar pelo diagnóstico de novo")

        if not perfil.get("prioridade") and not any(
            memoria.get(c) for c in ("necessidades", "desejos", "compras", "lista_mercado", "precos")
        ):
            st.caption("Ainda estou te conhecendo. Conversa comigo que eu vou lembrando.")


def _tela_boas_vindas(usuario_id, desde_id):
    """Tela de abertura de cada analise nova: fundo branco, a logo da marca e a
    pergunta direta. Sem barra lateral, sem cartoes, sem historico visivel.
    Assim que a pessoa manda a primeira mensagem (voz ou texto), a tela normal
    do chat assume, com os cartoes e a memoria.

    (A esfera azul e os blocos animados do logo, versoes anteriores desta tela,
    seguem guardados nos assets caso a fundadora queira retomar.)
    """
    # Centralizacao de verdade, nao "padding-top: 20vh" chutado: esse chute
    # calculava a partir da tela inteira, ignorando que a barra de digitar
    # fica fixa embaixo. Em celular (tela alta e estreita) sobrava um vao
    # gigante vazio entre a pergunta e a barra. Aqui o proprio container
    # principal do Streamlit (stMainBlockContainer) vira flex e cresce
    # (flex:1) pra preencher exatamente o espaco que sobra entre o topo e a
    # barra fixa, e so entao centraliza o conteudo dentro desse espaco real.
    # So se aplica nesta tela porque o <style> so existe enquanto esta
    # funcao roda (Streamlit remonta o DOM a cada tela).
    # O Streamlit tambem injeta um spacer proprio (uma div sem testid, irma
    # do bloco principal) que competia pelo mesmo espaco flexivel e sobrava
    # com a maior parte dele. Zerado aqui pra sobrar tudo pro nosso bloco.
    # (O stVerticalBlock de dentro tambem e flex:1 por padrao do proprio
    # Streamlit e preenche o container inteiro, entao o justify-content que
    # de fato centraliza o conteudo tem que ir nele, nao so no pai.)
    st.markdown(
        '<style>[data-testid="stMainBlockContainer"]{'
        "display:flex; flex-direction:column; flex:1;"
        "}"
        '[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"]{'
        "justify-content:center;"
        "}"
        '[data-testid="stAppScrollToBottomContainer"] > div:not([data-testid]){'
        "flex:0 0 auto !important;"
        "}</style>",
        unsafe_allow_html=True,
    )
    # So o simbolo aqui, sem o lockup completo (nome + "by IAgilize" +
    # tracinho): numa tela sem mais nada, o lockup inteiro pesa mais que a
    # propria pergunta, que e a acao real. A marca ja fica reforcada no
    # cabecalho cheio (_cabecalho_logo) assim que a conversa comeca.
    conteudo = (
        '<div style="display:flex; flex-direction:column; align-items:center; '
        'justify-content:center;">'
        f'<img src="data:image/png;base64,{_ICONE_B64}" '
        'style="height:40px; width:auto; opacity:0.85;" />'
        f'<p style="font-size:30px; font-weight:700; letter-spacing:-0.4px; '
        f'line-height:1.3; margin-top:20px; color:{COR_TEXTO_CLARO}; '
        'text-align:center; max-width:320px;">O que você quer comprar hoje?</p>'
        '</div>'
    )
    st.markdown(conteudo, unsafe_allow_html=True)

    # Acesso direto ao painel ja na primeira tela: quem so quer ver os
    # numeros nao precisa mandar mensagem antes pra barra lateral aparecer.
    # Atalho secundario de proposito: pilula fantasma no canto superior
    # direito, fora do caminho da acao principal (dizer o que quer comprar).
    # Visual da pilula: vidro escuro com borda em gradiente laranja (truque
    # dos dois backgrounds: o de dentro cobre o padding-box, o gradiente
    # aparece so na moldura via border-box). Sem animacao: um pulso continuo
    # e, por definicao, uma tecnica pra puxar o olho, o que brigava com o
    # pedido de ficar secundario. O brilho fica so no hover, como resposta a
    # interacao, nao como chamariz o tempo todo.
    st.markdown(
        "<style>"
        ".st-key-painel_boas_vindas{position:fixed; top:64px; right:28px; width:auto; z-index:99;}"
        ".st-key-painel_boas_vindas button{"
        "background:linear-gradient(rgba(12,29,46,0.92), rgba(12,29,46,0.92)) padding-box, "
        "linear-gradient(90deg, #FF8A00, #FFD166) border-box; "
        "border:1px solid transparent; border-radius:999px; "
        "padding:8px 20px; font-size:13px; font-weight:600; "
        f"color:{COR_TEXTO_CLARO}; "
        "box-shadow:0 0 10px rgba(255,138,0,0.18); "
        "transition:transform 0.15s ease, box-shadow 0.15s ease;}"
        ".st-key-painel_boas_vindas button:hover{"
        f"color:{COR_LARANJA}; transform:translateY(-1px); "
        "box-shadow:0 0 24px rgba(255,138,0,0.5);}"
        "</style>",
        unsafe_allow_html=True,
    )
    if st.button("📊 Meu painel", key="painel_boas_vindas"):
        st.session_state.tela = "painel"
        st.rerun()

    _estilizar_microfone("voz_boas_vindas")
    falado = speech_to_text(
        language="pt",
        start_prompt="🎤",
        stop_prompt="🔴",
        just_once=True,
        use_container_width=True,
        key="voz_boas_vindas",
    )
    digitado = st.chat_input("fala ou escreve o que quer comprar")
    _autofoco('div[data-testid="stChatInput"] textarea')

    entrada = digitado or falado
    if entrada:
        _processar_entrada(usuario_id, entrada, desde_id)


def _reais(valor):
    # Sem o escape "R\$" usado no markdown puro (barra_lateral): aqui o valor
    # sempre entra dentro de HTML bruto (os tiles do painel), que nao reprocessa
    # esse escape e mostraria a barra invertida literal na tela.
    return f"R$ {valor:.2f}".replace(".", ",")


# Par (inicio, fim) de cada cor de destaque, usado nos aneis em SVG e nos
# numeros grandes com texto em gradiente. Da o acabamento "moderninho" pedido
# pela fundadora em vez de traco solido de uma cor so.
_GRADIENTES = {
    COR_LARANJA: ("#FF8A00", "#FFD166"),
    COR_VERMELHO: ("#EF4444", "#F59E0B"),
    COR_AMARELO: ("#F5A623", "#FFD166"),
    COR_VERDE: ("#16A34A", "#5EEAD4"),
    COR_AZUL_INFO: ("#3B82F6", "#A855F7"),
}

# Contador global de ids de gradiente SVG: cada anel/donut na tela precisa de
# um id unico, senao o navegador reusa o primeiro <linearGradient> com aquele
# id e todos os cartoes ficam com a cor do primeiro gradiente desenhado.
_contador_gradiente = itertools.count()


# O painel inteiro e UM bloco HTML com CSS grid de 12 colunas (mosaico estilo
# "bento", como a referencia de dashboard fintech que a fundadora mandou).
# st.columns nao serve aqui: o espacamento dele e largo e as caixas saem
# todas do mesmo tamanho, matando a assimetria pedida.
_CSS_PAINEL = (
    "<style>"
    # O container central do Streamlit e estreito (~730px) por padrao, bom pro
    # chat mas sufocante pro mosaico. Alarga so enquanto o painel esta na tela
    # (este <style> so e renderizado na tela do painel).
    '[data-testid="stMainBlockContainer"]{max-width:1180px;}'
    ".gpainel{display:grid; grid-template-columns:repeat(12,1fr); gap:14px;}"
    ".gtile{position:relative; overflow:hidden; "
    "background:linear-gradient(160deg, rgba(255,255,255,0.09), rgba(255,255,255,0.02)); "
    f"border:1px solid {VIDRO_BORDA}; border-radius:20px; padding:18px 20px; "
    "box-shadow:0 14px 32px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05); "
    "backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);}"
    f".gsec{{grid-column:1/-1; color:{COR_LARANJA}; font-weight:700; font-size:12px; "
    "text-transform:uppercase; letter-spacing:0.8px; margin:10px 0 -4px;}"
    ".sp3{grid-column:span 3}.sp4{grid-column:span 4}.sp6{grid-column:span 6}"
    ".sp8{grid-column:span 8}.sp12{grid-column:span 12}"
    # Telas estreitas (celular): pares viram coluna unica, minis viram 2 por linha.
    "@media (max-width:820px){.sp3{grid-column:span 6 !important}"
    ".sp4,.sp6,.sp8{grid-column:span 12 !important}}"
    "</style>"
)


def _tile(span, conteudo, accent=None):
    """Um cartao do mosaico. accent liga o brilho colorido desfocado no canto;
    sem accent o cartao fica apagado (usado nos padroes ainda bloqueados)."""
    glow = ""
    if accent:
        glow = (
            f'<div style="position:absolute; top:-40px; right:-40px; width:140px; height:140px; '
            f'background:{accent}; opacity:0.17; filter:blur(36px); border-radius:50%; '
            f'pointer-events:none;"></div>'
        )
    return (
        f'<div class="gtile sp{span}">{glow}'
        f'<div style="position:relative; z-index:1; color:{COR_TEXTO_CLARO};">{conteudo}</div></div>'
    )


def _rotulo_tile(texto):
    return (
        '<div style="color:rgba(255,255,255,0.55); font-weight:700; font-size:11px; '
        'text-transform:uppercase; letter-spacing:0.8px; margin-bottom:10px;">'
        f"{html.escape(texto)}</div>"
    )


def _orbe(texto, sub, quente=False):
    """Esfera brilhante central do painel (o elemento hero da referencia
    visual): gradiente radial simulando volume + halo de luz da cor do estado.
    """
    if quente:
        grad = "radial-gradient(circle at 32% 28%, #FCA5A5 0%, #EF4444 55%, #7F1D1D 100%)"
        brilho = "rgba(239,68,68,0.5)"
    else:
        grad = "radial-gradient(circle at 32% 28%, #FFD9A0 0%, #FF9E2C 48%, #D96700 80%, #8A4300 100%)"
        brilho = "rgba(255,138,0,0.5)"
    return (
        f'<div style="width:150px; height:150px; border-radius:50%; margin:10px auto 14px; '
        f"background:{grad}; box-shadow:0 0 70px {brilho}, 0 24px 48px rgba(0,0,0,0.45), "
        f'inset -10px -14px 34px rgba(0,0,0,0.30); display:flex; align-items:center; '
        f'justify-content:center;">'
        f'<div style="text-align:center; color:#fff; text-shadow:0 2px 10px rgba(0,0,0,0.35);">'
        f'<div style="font-size:36px; font-weight:800; line-height:1;">{texto}</div>'
        f'<div style="font-size:10px; letter-spacing:1px; opacity:0.85; text-transform:uppercase; '
        f'margin-top:4px;">{sub}</div></div></div>'
    )


def _texto_gradiente(texto_html, cor, tamanho=32, peso=800):
    inicio, fim = _GRADIENTES.get(cor, (cor, cor))
    return (
        f'<span style="font-size:{tamanho}px; font-weight:{peso}; '
        f'background:linear-gradient(90deg, {inicio}, {fim}); '
        f'-webkit-background-clip:text; background-clip:text; '
        f'-webkit-text-fill-color:transparent; display:inline-block;">{texto_html}</span>'
    )


def _anel_svg(fatias, tamanho=140, espessura=16, cor_vazio="rgba(255,255,255,0.10)"):
    """Anel em SVG (stroke-dasharray por fatia). fatias: lista de (percentual, cor).
    Um unico item preenche o anel inteiro ate o percentual (gauge); varios itens
    dividem o anel em segmentos lado a lado (donut). Cada fatia usa gradiente
    de verdade (nao cor solida), definido em _GRADIENTES.
    """
    raio = (tamanho - espessura) / 2
    centro = tamanho / 2
    circunferencia = 2 * 3.14159265 * raio
    defs = []
    partes = [
        f'<circle cx="{centro}" cy="{centro}" r="{raio}" fill="none" '
        f'stroke="{cor_vazio}" stroke-width="{espessura}" />'
    ]
    offset = 0.0
    for percentual, cor in fatias:
        if percentual <= 0:
            continue
        inicio, fim = _GRADIENTES.get(cor, (cor, cor))
        gid = f"anel{next(_contador_gradiente)}"
        defs.append(
            f'<linearGradient id="{gid}" x1="0%" y1="0%" x2="100%" y2="100%">'
            f'<stop offset="0%" stop-color="{inicio}" /><stop offset="100%" stop-color="{fim}" />'
            f"</linearGradient>"
        )
        comprimento = circunferencia * min(percentual, 1.0)
        partes.append(
            f'<circle cx="{centro}" cy="{centro}" r="{raio}" fill="none" '
            f'stroke="url(#{gid})" stroke-width="{espessura}" stroke-linecap="round" '
            f'stroke-dasharray="{comprimento:.1f} {circunferencia - comprimento:.1f}" '
            f'stroke-dashoffset="{-offset:.1f}" '
            f'transform="rotate(-90 {centro} {centro})" />'
        )
        offset += comprimento
    defs_html = f"<defs>{''.join(defs)}</defs>" if defs else ""
    return f'<svg width="{tamanho}" height="{tamanho}" viewBox="0 0 {tamanho} {tamanho}">{defs_html}' + "".join(partes) + "</svg>"


def _anel_com_texto(fatias, texto_central, legenda_central, tamanho=140, espessura=16, tamanho_fonte=22):
    anel = _anel_svg(fatias, tamanho=tamanho, espessura=espessura)
    return (
        f'<div style="position:relative; width:{tamanho}px; height:{tamanho}px; flex-shrink:0; '
        f'margin:0 auto;">'
        f"{anel}"
        f'<div style="position:absolute; inset:0; display:flex; flex-direction:column; '
        f'align-items:center; justify-content:center; text-align:center;">'
        f'<div style="font-size:{tamanho_fonte}px; font-weight:800; color:{COR_TEXTO_CLARO};">{texto_central}</div>'
        f'<div style="font-size:10px; opacity:0.6; text-transform:uppercase; letter-spacing:0.4px;">{legenda_central}</div>'
        f"</div></div>"
    )


def _grafico_barras(dias, cor, altura=110):
    """Barras de gasto por dia do mes, em SVG com gradiente. Dias sem gasto
    aparecem como um toco apagado, pra regua do mes inteiro ficar visivel
    (mesma linguagem do grafico grande da referencia visual).
    """
    n = len(dias) or 1
    maior = max(dias) or 1.0
    largura = 520
    passo = largura / n
    lbarra = passo * 0.58
    inicio, fim = _GRADIENTES.get(cor, (cor, cor))
    gid = f"barras{next(_contador_gradiente)}"
    barras = []
    for i, v in enumerate(dias):
        if v > 0:
            h = max(8.0, v / maior * (altura - 12))
            opacidade = "1"
        else:
            h = 4.0
            opacidade = "0.22"
        x = i * passo + (passo - lbarra) / 2
        barras.append(
            f'<rect x="{x:.1f}" y="{altura - h:.1f}" width="{lbarra:.1f}" height="{h:.1f}" '
            f'rx="2" fill="url(#{gid})" opacity="{opacidade}"/>'
        )
    return (
        f'<svg viewBox="0 0 {largura} {altura}" preserveAspectRatio="none" '
        f'style="width:100%; height:{altura}px; display:block; margin-top:12px;">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="1" x2="0" y2="0">'
        f'<stop offset="0%" stop-color="{inicio}"/><stop offset="100%" stop-color="{fim}"/>'
        f"</linearGradient></defs>" + "".join(barras) + "</svg>"
    )


def _tile_termometro(term):
    rotulo = _rotulo_tile("Termômetro do mês")
    if not term["limite_definido"]:
        corpo = (
            f"<div>{_texto_gradiente(_reais(term['gasto_mes']), COR_LARANJA, tamanho=30)}</div>"
            '<div style="opacity:0.65; font-size:12px; margin-top:8px;">Ainda não sei seu limite '
            'mensal. Me conta na conversa ("meu limite é 2000") que eu acompanho aqui.</div>'
        )
        return _tile(4, rotulo + corpo, accent=COR_LARANJA)
    pct = round(term["percentual"] * 100)
    orbe = _orbe(f"{pct}%", "do limite", quente=term["estourou"])
    rodape = (
        f'<div style="text-align:center; font-size:13px;">'
        f'<b>{_reais(term["gasto_mes"])}</b> <span style="opacity:0.55;">de {_reais(term["limite"])}</span></div>'
    )
    if term["estourou"]:
        rodape += (
            '<div style="text-align:center; color:#FCA5A5; font-size:12px; margin-top:4px;">'
            "Passou do limite esse mês.</div>"
        )
    return _tile(4, rotulo + orbe + rodape, accent=(COR_VERMELHO if term["estourou"] else COR_LARANJA))


def _tile_grafico(gd, term):
    rotulo = _rotulo_tile("Gasto ao longo do mês")
    cabeca = (
        f"<div>{_texto_gradiente(_reais(term['gasto_mes']), COR_LARANJA, tamanho=30)}"
        f'<span style="opacity:0.6; font-size:12px; margin-left:12px;">'
        f'{term["dias_restantes"]} dias restantes no mês</span></div>'
    )
    grafico = _grafico_barras(gd["dias"], COR_LARANJA)
    regua = (
        '<div style="display:flex; justify-content:space-between; font-size:10px; '
        'opacity:0.45; margin-top:6px;">'
        f'<span>dia 1</span><span>hoje: dia {gd["dia_hoje"]}</span><span>dia {len(gd["dias"])}</span></div>'
    )
    return _tile(8, rotulo + cabeca + grafico + regua, accent=COR_LARANJA)


_NOMES_CATEGORIA = {
    "necessidade": "Necessidade",
    "desejo": "Desejo",
    "impulso": "Impulso",
    "mercado": "Mercado",
}
_CORES_CATEGORIA = {
    "necessidade": COR_AZUL_INFO,
    "desejo": COR_LARANJA,
    "impulso": COR_VERMELHO,
    "mercado": COR_VERDE,
}


def _tile_donut(dados):
    rotulo = _rotulo_tile("De onde veio o gasto")
    if not dados["tem_dado"]:
        corpo = '<div style="opacity:0.6; font-size:13px;">Ainda não tenho compra registrada esse mês.</div>'
        return _tile(4, rotulo + corpo, accent=COR_AZUL_INFO)

    fatias_com_valor = [f for f in dados["fatias"] if f["valor"] > 0]
    donut = _anel_com_texto(
        [(f["percentual"], _CORES_CATEGORIA[f["categoria"]]) for f in fatias_com_valor],
        _reais(dados["total"]),
        "no mês",
        tamanho=104,
        espessura=16,
        tamanho_fonte=14,
    )
    legenda = "".join(
        f'<div style="display:flex; justify-content:space-between; gap:10px; padding:3px 0; font-size:12px;">'
        f'<span><span style="color:{_CORES_CATEGORIA[f["categoria"]]};">●</span> '
        f'{_NOMES_CATEGORIA[f["categoria"]]}</span>'
        f'<span style="opacity:0.8;">{round(f["percentual"] * 100)}%</span></div>'
        for f in fatias_com_valor
    )
    corpo = donut + f'<div style="margin-top:12px;">{legenda}</div>'
    return _tile(4, rotulo + corpo, accent=COR_AZUL_INFO)


def _tile_segurado(dados):
    rotulo = _rotulo_tile("Dinheiro que o Guardião segurou")
    if not dados["tem_dado"]:
        corpo = (
            '<div style="opacity:0.6; font-size:13px;">Ainda não tenho comparação de preço em '
            "nenhuma compra sua. Quando você citar uma cotação antes de comprar, eu registro e "
            "mostro aqui quanto você poupou.</div>"
        )
        return _tile(8, rotulo + corpo, accent=COR_VERDE)

    itens_html = "".join(
        f'<div style="display:flex; justify-content:space-between; gap:10px; padding:3px 0; '
        f'font-size:12px; opacity:0.85; border-bottom:1px solid rgba(255,255,255,0.06);">'
        f'<span>{html.escape(str(i["item"]))}</span><span>{_reais(i["economia"])}</span></div>'
        for i in dados["itens"][:4]
    )
    corpo = (
        '<div style="display:flex; align-items:center; gap:28px; flex-wrap:wrap;">'
        f"<div>{_texto_gradiente(_reais(dados['total']), COR_VERDE, tamanho=40)}"
        '<div style="opacity:0.6; font-size:12px;">economizados comparando preço antes de comprar</div></div>'
        f'<div style="flex:1; min-width:170px;">{itens_html}</div></div>'
    )
    return _tile(8, rotulo + corpo, accent=COR_VERDE)


def _barra_mini(percentual, cor):
    return (
        '<div style="background:rgba(255,255,255,0.10); border-radius:6px; height:7px; '
        'margin-top:10px; overflow:hidden;">'
        f'<div style="background:{cor}; width:{min(percentual * 100, 100):.0f}%; height:100%;"></div>'
        "</div>"
    )


_CORES_PADRAO = {
    "impulso": COR_VERMELHO,
    "abandono": COR_AMARELO,
    "parcelas": COR_LARANJA,
    "cruzamento": COR_VERMELHO,
    "recorrencia": COR_AZUL_INFO,
    "cacador": COR_VERDE,
}

# Legenda curta dentro/abaixo dos mini-medidores radiais dos padroes de %.
_SUB_RADIAL = {"impulso": "das compras", "abandono": "das avaliadas", "cruzamento": "dos impulsos"}
_LEGENDA_RADIAL = {
    "impulso": "{q} de {t} compras foram por impulso",
    "abandono": "{q} de {t} avaliadas sem uso ou arrependidas",
    "cruzamento": "{q} de {t} impulsos deram errado",
}


def _tile_padrao_html(p, span):
    chave = p["chave"]
    cor = _CORES_PADRAO.get(chave, COR_LARANJA)
    rotulo = _rotulo_tile(p["titulo"])

    if not p.get("pronto"):
        minimo = p.get("minimo")
        progresso = p.get("progresso", 0)
        if minimo:
            # O anel cinza mostra quantos dados ja tem (2/3, 1/5...). Sem a
            # palavra "desbloquear": o padrao pode ser uma noticia ruim (voce
            # compra por impulso, voce se arrepende direto), entao soaria como
            # premio abrir ele. E so uma questao de nao ter dado suficiente
            # ainda pra falar com confianca, nada de conquista.
            anel = _anel_com_texto(
                [(progresso / minimo, "rgba(255,255,255,0.35)")],
                f"{progresso}/{minimo}",
                "dados",
                tamanho=92,
                espessura=10,
                tamanho_fonte=18,
            )
            corpo = anel + (
                '<div style="text-align:center; opacity:0.5; font-size:11px; margin-top:8px;">'
                "Ainda não tenho dado suficiente aqui.</div>"
            )
        elif chave == "parcelas":
            corpo = '<div style="opacity:0.55; font-size:13px;">Nenhuma parcela em aberto no momento.</div>'
        else:
            corpo = '<div style="opacity:0.55; font-size:13px;">Ainda não tenho dado suficiente aqui.</div>'
        return _tile(span, rotulo + corpo)

    if chave in ("impulso", "abandono", "cruzamento"):
        anel = _anel_com_texto(
            [(p["percentual"], cor)],
            f"{round(p['percentual'] * 100)}%",
            _SUB_RADIAL[chave],
            tamanho=92,
            espessura=10,
            tamanho_fonte=22,
        )
        legenda = _LEGENDA_RADIAL[chave].format(q=p["quantidade"], t=p["total"])
        corpo = anel + (
            f'<div style="text-align:center; opacity:0.6; font-size:11px; margin-top:8px;">{legenda}</div>'
        )
        return _tile(span, rotulo + corpo, accent=cor)

    if chave == "cacador":
        plural = "item" if p["quantidade_itens"] == 1 else "itens"
        corpo = (
            f"<div>{_texto_gradiente(_reais(p['total_economizado']), COR_VERDE, tamanho=28)}</div>"
            f'<div style="opacity:0.65; font-size:12px; margin-top:6px;">'
            f'comparando preço, em {p["quantidade_itens"]} {plural}</div>'
        )
        return _tile(span, rotulo + corpo, accent=COR_VERDE)

    if chave == "parcelas":
        ativas = p["parcelas_ativas"]
        sub = (
            html.escape(str(ativas[0]["item"]))
            if len(ativas) == 1
            else f"{len(ativas)} parcelamentos ativos"
        )
        corpo = (
            f"<div>{_texto_gradiente(_reais(p['compromisso_mensal']) + '/mês', COR_LARANJA, tamanho=26)}</div>"
            f'<div style="opacity:0.65; font-size:12px; margin:4px 0 8px;">{sub}</div>'
        )
        if p["percentual_do_limite"]:
            corpo += _barra_mini(p["percentual_do_limite"], cor)
            corpo += (
                f'<div style="opacity:0.55; font-size:11px; margin-top:6px;">'
                f'{round(p["percentual_do_limite"] * 100)}% do seu limite mensal já comprometido</div>'
            )
        return _tile(span, rotulo + corpo, accent=cor)

    if chave == "recorrencia":
        item = p["itens"][0]
        extra = (
            f' <span style="opacity:0.5;">+{len(p["itens"]) - 1}</span>' if len(p["itens"]) > 1 else ""
        )
        seta = " · comprando com mais frequência" if item["intervalo_encurtando"] else ""
        corpo = (
            f'<div style="font-size:22px; font-weight:800;">{_reais(item["preco_inicial"])} '
            f'<span style="color:{COR_LARANJA};">→</span> {_reais(item["preco_atual"])}</div>'
            f'<div style="opacity:0.65; font-size:12px; margin-top:6px;">'
            f'{html.escape(str(item["item"]))}{extra}{seta}</div>'
        )
        return _tile(span, rotulo + corpo, accent=cor)

    return _tile(span, rotulo)


def _tela_painel(usuario_id):
    """Tela do painel financeiro (Fase 2 do roadmap, ver PROJETO.md secao 9).
    Troca a tela principal por inteiro, sem mexer no fluxo de conversa: quem
    volta pro chat encontra tudo exatamente como deixou.

    O painel e UM bloco HTML com CSS grid de 12 colunas (mosaico bento,
    seguindo a referencia visual da fundadora): orbe hero + grafico grande
    na linha 1, donut + numero de prova de valor na linha 2, e os padroes
    como tiles densos com mini-medidores radiais.
    """
    _cabecalho_logo()
    if st.button("← Voltar pro chat"):
        st.session_state.tela = "chat"
        st.rerun()

    dados = painel.montar_painel(mem.ler_memoria(usuario_id))
    padroes = {p["chave"]: p for p in dados["padroes"]}

    tiles = [
        _tile_termometro(dados["termometro"]),
        _tile_grafico(dados["gasto_diario"], dados["termometro"]),
        _tile_donut(dados["origem_gasto"]),
        _tile_segurado(dados["dinheiro_segurado"]),
        '<div class="gsec">Padrões de consumo</div>',
        _tile_padrao_html(padroes["impulso"], 3),
        _tile_padrao_html(padroes["abandono"], 3),
        _tile_padrao_html(padroes["cruzamento"], 3),
        _tile_padrao_html(padroes["cacador"], 3),
        _tile_padrao_html(padroes["parcelas"], 6),
        _tile_padrao_html(padroes["recorrencia"], 6),
    ]
    st.markdown(
        _CSS_PAINEL
        + '<div style="font-size:26px; font-weight:800; margin:6px 0 14px; '
        f'color:{COR_TEXTO_CLARO};">Meu painel</div>'
        + f'<div class="gpainel">{"".join(tiles)}</div>',
        unsafe_allow_html=True,
    )


def tela_do_chat():
    usuario_id = st.session_state.usuario_id

    # Mostra so a conversa desta sessao: a tela abre limpa a cada uso.
    desde_id = st.session_state.get("sessao_desde_id", 0)
    historico = mem.ler_mensagens(usuario_id, desde_id)

    if not historico:
        _tela_boas_vindas(usuario_id, desde_id)
        return

    _cabecalho_logo()
    barra_lateral(usuario_id)

    for m in historico:
        avatar = AVATAR_ASSISTENTE if m["papel"] == "assistant" else _avatar_usuario(usuario_id)
        with st.chat_message(m["papel"], avatar=avatar):
            if m["papel"] == "assistant":
                mostrar_resposta(m["conteudo"])
            else:
                st.markdown(m["conteudo"])

    # Depois de um diagnostico (a ultima resposta trouxe os tres rotulos),
    # oferece botoes de decisao em vez de deixar so o chat aberto. A pessoa
    # decide ali mesmo; se quiser detalhar mais, o campo de texto continua
    # disponivel, mas o padrao nao e ficar no vai e volta.
    diagnostico_atual = (
        _extrair_rotulos(historico[-1]["conteudo"])
        if historico and historico[-1]["papel"] == "assistant"
        else None
    )
    if diagnostico_atual is not None:
        _, rotulos_atuais, _ = diagnostico_atual
        # A "Motivação da compra" resume o item bem melhor que a ultima frase
        # digitada (que pode ser so uma resposta curta tipo "10" ou "sim").
        resumo = rotulos_atuais.get("Motivação da compra") or _ultima_fala_do_usuario(historico)
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ Vou comprar", use_container_width=True):
                mem.registrar_decisao(usuario_id, resumo, "comprou")
                mem.salvar_mensagem(usuario_id, "assistant", "Boa. Decisão registrada, aproveita.")
                st.rerun()
        with col2:
            if st.button("⏳ Vou esperar", use_container_width=True):
                mem.registrar_decisao(usuario_id, resumo, "esperou")
                mem.salvar_mensagem(
                    usuario_id, "assistant", "Boa escolha. Volta quando quiser reavaliar."
                )
                st.rerun()
        with col3:
            if st.button("🔍 Quero comparar antes", use_container_width=True):
                mem.registrar_decisao(usuario_id, resumo, "vai comparar")
                mem.salvar_mensagem(
                    usuario_id, "assistant", "Combinado. Traz as opções que quiser comparar."
                )
                st.rerun()

    _estilizar_microfone("voz")
    falado = speech_to_text(
        language="pt",
        start_prompt="🎤",
        stop_prompt="🔴",
        just_once=True,
        use_container_width=True,
        key="voz",
    )
    # Caixa de texto, para quem preferir digitar.
    digitado = st.chat_input("fala ou escreve antes de comprar")
    _autofoco('div[data-testid="stChatInput"] textarea')

    # A entrada pode vir da voz ou do teclado.
    entrada = digitado or falado
    if entrada:
        atalho = _resposta_lista_mercado(usuario_id, entrada)
        if atalho is not None:
            mem.salvar_mensagem(usuario_id, "user", entrada)
            mem.salvar_mensagem(usuario_id, "assistant", atalho)
            st.rerun()
        elif mem.contar_mensagens_usuario_hoje(usuario_id) >= LIMITE_DIA:
            st.warning(
                "Você já conversou bastante comigo hoje. Volta amanhã que eu te espero, "
                "com tudo que já lembro de você guardado."
            )
        else:
            mem.salvar_mensagem(usuario_id, "user", entrada)
            with st.chat_message("user", avatar=_avatar_usuario(usuario_id)):
                st.markdown(entrada)
            with st.chat_message("assistant", avatar=AVATAR_ASSISTENTE):
                with st.spinner("pensando..."):
                    modelo = st.session_state.get("modelo", cerebro.MODELO)
                    resposta = cerebro.responder(usuario_id, modelo, desde_id)
                mostrar_resposta(resposta)
            mem.salvar_mensagem(usuario_id, "assistant", resposta)
            st.rerun()


def _perfil_incompleto(memoria):
    """True quando a pessoa ainda nao passou pelo perfil rapido (nem prioridade
    nem guardrails preenchidos). Quem ja tem qualquer um dos dois (inclusive de
    versoes antigas) nao ve o formulario de novo."""
    perfil = memoria.get("perfil", {})
    return not perfil.get("prioridade") and not perfil.get("guardrails")


def _tela_perfil_rapido(usuario_id):
    """Onboarding objetivo: a pessoa marca opcoes prontas (e detalha em campos
    abertos so quando quer), em vez de responder um campo aberto do zero. Salva
    o resultado em perfil.prioridade e perfil.guardrails e segue pro chat.
    """
    nome = st.session_state.get("nome", "").strip()
    _cabecalho_logo()
    saudacao = f"Oi, {nome}. " if nome else ""
    st.markdown(f"{saudacao}Antes de começar, um perfil rápido pra eu te ajudar melhor.")

    st.markdown("#### O que você mais quer proteger no seu dinheiro?")
    st.caption("Pode marcar mais de uma.")
    marcadas_prio = []
    objetivo = ""
    for opcao in OPCOES_PRIORIDADE:
        if st.checkbox(opcao, key=f"prio_{opcao}"):
            marcadas_prio.append(opcao)
            if opcao == OPCAO_OBJETIVO:
                objetivo = st.text_input(
                    "Qual objetivo?",
                    key="objetivo",
                    placeholder="ex: trocar o carro, uma viagem, uma reserva",
                )
    detalhe = st.text_input(
        "Quer detalhar? (opcional)",
        key="detalhe_prioridade",
        placeholder="algo mais que eu deva saber",
    )

    st.markdown("#### Tem algo que eu deva levar em conta nas suas compras?")
    st.caption("Pode marcar mais de uma.")
    marcadas_guard = []
    for opcao in OPCOES_GUARDRAILS:
        if st.checkbox(opcao, key=f"guard_{opcao}"):
            marcadas_guard.append(opcao)
    outro_guard = st.text_input(
        "Outro (opcional)",
        key="outro_guardrail",
        placeholder="algum limite ou situação sua",
    )

    st.markdown("#### Tem um limite de gasto mensal? (opcional)")
    st.caption("Pode deixar em branco e me contar depois, numa conversa.")
    limite_mensal = st.number_input(
        "Limite mensal em reais",
        key="limite_mensal",
        min_value=0.0,
        step=50.0,
        format="%.2f",
        label_visibility="collapsed",
    )

    st.write("")
    if st.button("Começar", type="primary"):
        # Monta a prioridade a partir das opcoes marcadas. A opcao de objetivo,
        # quando preenchida, entra ja nomeada ("Juntar pra: trocar o carro").
        partes = []
        for opcao in marcadas_prio:
            if opcao == OPCAO_OBJETIVO and objetivo.strip():
                partes.append(f"Juntar dinheiro para: {objetivo.strip()}")
            else:
                partes.append(opcao)
        if detalhe.strip():
            partes.append(detalhe.strip())
        prioridade = ". ".join(partes) if partes else "Comprar com mais consciência"

        # Guardrails: as opcoes marcadas (menos "Nada disso agora") mais o campo
        # aberto. Se ficar vazio, guarda um marcador pra nao reperguntar depois.
        guardrails = [g for g in marcadas_guard if g != "Nada disso agora"]
        if outro_guard.strip():
            guardrails.append(outro_guard.strip())
        if not guardrails:
            guardrails = ["nenhum guardrail declarado ainda"]

        memoria = mem.ler_memoria(usuario_id)
        memoria.setdefault("perfil", {})
        memoria["perfil"]["prioridade"] = prioridade
        memoria["perfil"]["guardrails"] = guardrails
        if limite_mensal and limite_mensal > 0:
            memoria["perfil"]["limite_mensal"] = float(limite_mensal)
        mem.salvar_memoria(usuario_id, memoria)
        st.rerun()


# Guarda simples: sem chave de API, avisa antes de tentar conversar.
if not os.environ.get("ANTHROPIC_API_KEY"):
    _cabecalho_logo()
    st.warning(
        "Falta a chave da API da Anthropic. Crie um arquivo chamado .env na pasta "
        "do projeto com a linha:  ANTHROPIC_API_KEY=sua-chave-aqui  e recarregue."
    )
elif "usuario_id" not in st.session_state:
    # Se o nome ja estiver na URL (de uma entrada anterior no mesmo navegador),
    # recupera de la em vez de perguntar de novo. A memoria persiste no banco
    # independente disso, mas isso evita reperguntar o nome a cada reload.
    _nome_na_url = st.query_params.get("usuario")
    if _nome_na_url:
        st.session_state.usuario_id = _nome_na_url.strip().lower()
        st.session_state.nome = _nome_na_url.strip()
        st.session_state.sessao_desde_id = mem.ultimo_id(st.session_state.usuario_id)
        st.rerun()
    else:
        tela_de_entrada()
else:
    _memoria_atual = mem.ler_memoria(st.session_state.usuario_id)
    if _perfil_incompleto(_memoria_atual):
        _tela_perfil_rapido(st.session_state.usuario_id)
    elif st.session_state.get("tela") == "painel":
        _tela_painel(st.session_state.usuario_id)
    else:
        tela_do_chat()
