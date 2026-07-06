# Contexto do MVP do Guardião — leia primeiro

> Handoff consolidado para o Project "MVP do Guardião" no claude.ai.
> Suba este arquivo em Project knowledge OU cole no início de uma conversa nova.
> Atualizado em 2026-07-04.

---

## 1. O que é o Guardião

Produto de IA que ajuda a pessoa a tomar melhores decisões de compra. O foco não é o menor preço, é a qualidade da decisão: comprar quando faz sentido, esperar quando não faz, e não cair em cilada.

A fundadora é solo e constrói o MVP com Claude Code. Regra guia: sempre a solução mais simples que valida a mesma hipótese.

## 2. O método (3 lentes)

1. Consciência de Compra → "Devo?" (necessidade x desejo, clareza, viabilidade financeira, estado emocional)
2. Comparador → "Qual?" (opções, critérios, preço entre alternativas)
3. Farejador de Ciladas → "É justo e seguro?" (fraude, abuso, orçamento de serviço tipo oficina)

## 3. Especificação Funcional v1.0 (independente de tecnologia)

- 6 dimensões: motivação, estado emocional, clareza, viabilidade, reversibilidade, risco externo.
- Tabela de decisão única com precedência.
- 6 vereditos: PODE COMPRAR, COMPARAR, CHECAR A OFERTA, ESFRIAR, REVER FINANÇAS, REPENSAR.
- Princípios: memória primeiro, veredito primeiro, retorno sempre disponível.

## 4. Diferencial central

Memória persistente. Os 3 GPTs originais da ChatGPT eram stateless. Sem memória, o produto é indistinguível do ChatGPT cru. Persistência é o objetivo do MVP e o real diferencial (DP-002 do Product Book).

## 5. Estado atual do MVP (2026-07-03/04)

Scaffold em `~/guardiao-mvp` (fora do repo de marketing fluxo-criativo).
- Stack: Python + Streamlit + SQLite (memória em `guardiao.db`) + Anthropic SDK com tool use (`salvar_memoria`).
- Modelo padrão `claude-opus-4-8` (env `GUARDIAO_MODELO` troca por sonnet).
- Arquivos: `app.py`, `guardiao/metodo.py` (system prompt = método v1), `guardiao/memoria.py`, `guardiao/cerebro.py`.
- Roda com `streamlit run app.py` após `pip install -r requirements.txt` e chave `ANTHROPIC_API_KEY` no `.env`.
- Memória testada, persiste entre sessões.

Roadmap: Dia 2 (3 lentes afiadas + detecção de duplicata), Dia 3 (onboarding + follow-up pós-compra), Dia 4 (PWA + deploy Streamlit Cloud). Deploy da fundadora é Vercel.

## 6. Decisões ainda abertas (da fundadora)

1. Monetização: assinatura x comissão de afiliado. Recomendação: assinatura, para preservar o posicionamento de confiança.
2. Escopo do Farejador no MVP. Recomendação: versão só com sinais visíveis.

## 7. Benchmark em andamento

Testando um concorrente pago (R$ 49/mês, R$ 319/ano na promo). Onboarding observado: tela "me conhecer" → tela "quem sou eu" → tela de hábitos. Detalhes e novas descobertas ficam em `benchmark-concorrentes.md`.

## 8. O que estava sendo feito nesta última conversa

Montando o Project "MVP do Guardião" no claude.ai para centralizar o trabalho do MVP, separado do repo de marketing. Foram gerados: as instruções do projeto (`instrucoes-do-projeto.md`), o documento de benchmark (`benchmark-concorrentes.md`) e este handoff.
