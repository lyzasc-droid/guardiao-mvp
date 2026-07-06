# Guardiao (MVP)

Uma IA que ajuda a tomar melhores decisoes de compra. Nao busca o menor preco,
busca a qualidade da decisao. Lembra de voce entre conversas.

## Como rodar (primeira vez)

1. Abra o Terminal na pasta do projeto.
2. Crie o ambiente e instale as dependencias:

   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Crie o arquivo da chave:

   ```
   cp .env.example .env
   ```

   Abra o `.env` e cole sua chave da Anthropic depois de `ANTHROPIC_API_KEY=`.
   (Voce pega a chave no console.anthropic.com, menu API Keys.)

4. Rode o app:

   ```
   streamlit run app.py
   ```

   O Guardiao abre no navegador. Digite um nome, converse, feche e reabra:
   ele lembra de voce.

## Nas proximas vezes

```
source .venv/bin/activate
streamlit run app.py
```

## O que tem aqui

- `app.py` — a tela de chat (Streamlit).
- `guardiao/metodo.py` — o Metodo do Guardiao (o cerebro, em texto).
- `guardiao/memoria.py` — a memoria que persiste (SQLite, arquivo guardiao.db).
- `guardiao/cerebro.py` — a conversa com o modelo da Anthropic.
