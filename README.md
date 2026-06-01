# 🌊 Agente Autônomo — "Vivendo em Ubatuba"

Pipeline de IA que busca notícias locais, gera legendas e publica no Instagram automaticamente.

## Arquitetura

```
[Tavily API] ──busca──▶ [Claude LLM] ──legenda──▶ [Instagram Graph API]
  notícias                filtra e                   publica post
  (24h)                   redige                     automaticamente
```

## Configuração Rápida

### 1. Instale as dependências
```bash
pip install requests python-dotenv
```

### 2. Configure as credenciais
```bash
cp .env.example .env
# Edite .env com suas chaves reais
```

### 3. Execute localmente
```bash
python agente_ubatuba.py
```

## Agendamento

### Opção A: GitHub Actions (recomendado — gratuito)
1. Suba este projeto para um repositório GitHub (pode ser privado)
2. Adicione seus secrets em: `Settings > Secrets > Actions`
3. O workflow em `.github/workflows/agente_ubatuba.yml` roda automaticamente às 08h BRT

### Opção B: PythonAnywhere (gratuito, sem precisar do GitHub)
1. Cadastre-se em https://www.pythonanywhere.com (plano free)
2. Faça upload dos arquivos
3. Vá em `Tasks` e adicione: `python /home/SEU_USER/agente_ubatuba.py`
4. Configure para rodar diariamente no horário desejado

### Opção C: CRON (Linux/Mac local ou VPS)
```bash
# Edite o crontab:
crontab -e

# Adicione esta linha (roda todo dia às 08:00):
0 8 * * * cd /caminho/para/projeto && python agente_ubatuba.py >> cron.log 2>&1
```

## Como Obter o Instagram Access Token

1. Acesse: https://developers.facebook.com
2. Crie um App → tipo "Business"
3. Adicione o produto "Instagram Graph API"
4. Vincule sua conta Instagram Business
5. Gere um Page Access Token de longa duração (~60 dias)
6. Use o Graph API Explorer para renovar quando necessário

> **Atenção:** A conta precisa ser do tipo **Business** ou **Creator**.  
> Contas pessoais não têm acesso à API de publicação.

## Renovação Automática do Token

O token do Instagram expira a cada 60 dias. Para automatizar a renovação:
```
GET https://graph.facebook.com/oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id={APP_ID}
  &client_secret={APP_SECRET}
  &fb_exchange_token={TOKEN_ATUAL}
```

Adicione essa lógica ao script ou configure um lembrete mensal.

## Estimativa de Custos (por mês)

| Serviço | Plano | Custo |
|---|---|---|
| Tavily API | Free (1.000 req/mês) | $0 |
| Anthropic (Claude) | Pay-as-you-go | ~$0,30/mês |
| Instagram Graph API | Gratuito | $0 |
| GitHub Actions | Gratuito | $0 |
| **Total** | | **~$0,30/mês** |

## Estrutura de Arquivos

```
vivendo_ubatuba/
├── agente_ubatuba.py        # Script principal
├── .env.example             # Template de configuração
├── .env                     # Suas credenciais (NÃO subir no GitHub!)
├── .gitignore               # Protege o .env
├── historico_posts.jsonl    # Log dos posts publicados
├── agente_ubatuba.log       # Log de execução detalhado
└── .github/
    └── workflows/
        └── agente_ubatuba.yml   # Agendamento via GitHub Actions
```
