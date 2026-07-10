# Guardião — instruções do projeto

Este é o projeto do **Guardião**, um produto de IA de apoio à decisão de compra. A fundadora é solo e não é programadora: entregue soluções prontas e explique em linguagem simples, sem jargão técnico. Sempre em Português do Brasil com acentuação correta.

## Regra de abertura de sessão

Ao iniciar QUALQUER conversa neste projeto, a primeira ação é **ler o arquivo `PROJETO.md`** (o cérebro do projeto) para carregar todo o contexto: o que é o produto, o método das 3 lentes, a spec v1.0, o estado do MVP, o roadmap, as decisões abertas e o benchmark.

## Regra de fechamento de sessão

Sempre que algo relevante mudar durante a conversa (uma decisão nova, uma tela nova, um aprendizado de benchmark, um passo do roadmap concluído), **atualize o `PROJETO.md`** antes de encerrar:
- Registre a mudança na seção 9 (Histórico de decisões e aprendizados) com a data.
- Atualize a seção que corresponde (estado do MVP, roadmap, benchmark, próximos passos).
- Atualize a data de "Última atualização" no topo.

Assim o projeto sempre se lembra dele mesmo entre sessões.

## Princípios do produto

- Priorizar sempre a solução mais simples que valida a mesma hipótese.
- Toda decisão de produto passa pela lente da confiança do usuário.
- O diferencial central é a memória persistente. Nunca abrir mão disso.

## Como rodar o app

Da pasta `meus-produtos/guardiao-mvp/`:

```
.venv/bin/streamlit run app.py
```

A `ANTHROPIC_API_KEY` e a `DATABASE_URL` (connection string do Postgres no Supabase) precisam estar no `.env` desta pasta. A memória persistente fica no Supabase, não mais em `guardiao.db` local (esse arquivo só existe como backup histórico pré-migração).

## Deploy

O ambiente de deploy da fundadora é a Vercel.
