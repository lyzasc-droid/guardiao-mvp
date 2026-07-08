"""Guardiao. App de chat que ajuda a tomar melhores decisoes de compra.

Roda com: streamlit run app.py
Precisa de ANTHROPIC_API_KEY no arquivo .env (ou no ambiente).
"""

import base64
import os
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from streamlit_mic_recorder import speech_to_text

from guardiao import cerebro
from guardiao import memoria as mem

CAMINHO_ASSETS = Path(__file__).resolve().parent / "assets"

# Marca do produto: so o simbolo (tijolinhos) da IAgilize, sem a palavra
# "IAgilize", mais o nome "Guardião do Bolso" ao lado. Icone carregado uma vez.
_ICONE_B64 = base64.b64encode((CAMINHO_ASSETS / "icone.png").read_bytes()).decode("ascii")


def _logo_html(altura_px, centralizado=False):
    """Simbolo + 'Guardião do Bolso'. altura_px e a altura do simbolo; o texto
    acompanha proporcionalmente. centralizado=True alinha ao centro (abertura).
    """
    fonte = round(altura_px * 0.62)
    justify = "center" if centralizado else "flex-start"
    return (
        f'<div style="display:flex; align-items:center; gap:12px; '
        f'justify-content:{justify}; margin-bottom:12px;">'
        f'<img src="data:image/png;base64,{_ICONE_B64}" style="height:{altura_px}px; width:auto;" />'
        f'<span style="font-size:{fonte}px; font-weight:600; color:#131B3A; '
        f'letter-spacing:-0.5px;">Guardião do Bolso</span>'
        f"</div>"
    )


def _cabecalho_logo():
    """Cabecalho padrao das telas: o simbolo + 'Guardião do Bolso'."""
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

st.set_page_config(page_title="Guardião", page_icon="🛡️", layout="centered")

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
        st.warning(f"**{aviso}**", icon="⚠️")
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
        with st.container(border=True):
            st.markdown(f"**{rotulo}**")
            st.markdown(valor)
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
        for titulo, chave in [
            ("Necessidades abertas", "necessidades"),
            ("Desejos", "desejos"),
            ("Compras recentes", "compras"),
        ]:
            itens = memoria.get(chave, [])
            if itens:
                st.markdown(f"**{titulo}**")
                for item in itens:
                    if isinstance(item, dict):
                        rotulo = item.get("item") or item.get("titulo") or item.get("nome") or str(item)
                    else:
                        rotulo = str(item)
                    st.write(f"- {rotulo}")
        if not perfil.get("prioridade") and not any(
            memoria.get(c) for c in ("necessidades", "desejos", "compras")
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
    conteudo = (
        '<div style="display:flex; flex-direction:column; align-items:center; '
        'justify-content:center; padding-top:20vh;">'
        f'{_logo_html(50, centralizado=True)}'
        '<p style="font-size:19px; margin-top:28px; '
        'text-align:center; max-width:280px;">O que você quer comprar hoje?</p>'
        '</div>'
    )
    st.markdown(conteudo, unsafe_allow_html=True)

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
        if mem.contar_mensagens_usuario_hoje(usuario_id) >= LIMITE_DIA:
            st.warning(
                "Você já conversou bastante comigo hoje. Volta amanhã que eu te espero, "
                "com tudo que já lembro de você guardado."
            )
        else:
            mem.salvar_mensagem(usuario_id, "user", entrada)
            with st.spinner("pensando..."):
                modelo = st.session_state.get("modelo", cerebro.MODELO)
                resposta = cerebro.responder(usuario_id, modelo, desde_id)
            mem.salvar_mensagem(usuario_id, "assistant", resposta)
            st.rerun()


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
        with st.chat_message(m["papel"]):
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
        if mem.contar_mensagens_usuario_hoje(usuario_id) >= LIMITE_DIA:
            st.warning(
                "Você já conversou bastante comigo hoje. Volta amanhã que eu te espero, "
                "com tudo que já lembro de você guardado."
            )
        else:
            mem.salvar_mensagem(usuario_id, "user", entrada)
            with st.chat_message("user"):
                st.markdown(entrada)
            with st.chat_message("assistant"):
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
    else:
        tela_do_chat()
