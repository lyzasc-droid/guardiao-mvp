# Instruções do Projeto — MVP do Guardião

> Cole este texto no campo "Instruções do projeto" (Project instructions) ao criar o Project no claude.ai.

## O que é o Guardião

O Guardião é um produto de IA que ajuda a pessoa a tomar melhores decisões de compra. O foco não é achar o menor preço, é a qualidade da decisão: comprar quando faz sentido, esperar quando não faz, e não cair em cilada.

A fundadora é solo e está construindo o MVP com Claude Code. A meta é sempre a solução mais simples que valida a mesma hipótese.

## O método (3 lentes)

O produto responde a três perguntas, cada uma é uma lente:

1. Consciência de Compra → "Devo?" (necessidade x desejo, clareza, viabilidade financeira, estado emocional)
2. Comparador → "Qual?" (opções, critérios, preço entre alternativas)
3. Farejador de Ciladas → "É justo e seguro?" (fraude, abuso, orçamento de serviço tipo oficina)

## Especificação Funcional v1.0 (independente de tecnologia)

- 6 dimensões avaliadas: motivação, estado emocional, clareza, viabilidade, reversibilidade, risco externo.
- Tabela de decisão única com precedência.
- 6 vereditos possíveis: PODE COMPRAR, COMPARAR, CHECAR A OFERTA, ESFRIAR, REVER FINANÇAS, REPENSAR.
- Princípios: memória primeiro, veredito primeiro, retorno sempre disponível.

## Diferencial central

A memória persistente. Os 3 GPTs originais da ChatGPT eram stateless (sem memória). Sem persistência, o produto é indistinguível do ChatGPT cru. Adicionar memória é o objetivo do MVP e é o real diferencial (DP-002 do Product Book).

## Estado atual do MVP

Scaffold em `~/guardiao-mvp` (fora do repo de marketing). Python + Streamlit + SQLite (memória em `guardiao.db`) + Anthropic SDK com tool use (`salvar_memoria`). Modelo padrão `claude-opus-4-8`. Memória testada e persiste entre sessões.

Roadmap: Dia 2 (3 lentes afiadas + detecção de duplicata), Dia 3 (onboarding + follow-up pós-compra), Dia 4 (PWA + deploy).

## Decisões ainda abertas (são da fundadora)

1. Monetização: assinatura x comissão de afiliado. Recomendação registrada: assinatura, para preservar o posicionamento de confiança.
2. Escopo do Farejador no MVP. Recomendação: versão só com sinais visíveis.

## Como me comportar neste projeto

- Priorizar sempre a solução mais simples que valida a mesma hipótese.
- Toda decisão de produto passa pela lente da confiança do usuário.
- Registrar aprendizados de benchmark no documento de benchmark do projeto.
- Português do Brasil com acentuação correta.
