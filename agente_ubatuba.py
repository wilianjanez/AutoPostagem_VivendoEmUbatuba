"""
=============================================================================
AGENTE AUTÔNOMO - "VIVENDO EM UBATUBA" (Instagram) — v3.1
=============================================================================
DEPENDÊNCIAS:  pip install requests python-dotenv Pillow
CONFIGURAÇÃO:  copie .env.example para .env e preencha suas credenciais
EXECUÇÃO:      python agente_ubatuba.py
=============================================================================
"""

import os, io, re, json, time, base64, logging, requests, random, ftplib, feedparser
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================
load_dotenv()
random.seed()  # seed baseado no tempo do sistema — garante aleatoriedade real

TAVILY_API_KEY    = os.getenv("TAVILY_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
IG_ACCESS_TOKEN   = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID        = os.getenv("IG_USER_ID")
IMGBB_API_KEY         = os.getenv("IMGBB_API_KEY")
YOUTUBE_CLIENT_ID     = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
OPENWEATHER_API_KEY   = os.getenv("OPENWEATHER_API_KEY")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_CX      = os.getenv("GOOGLE_SEARCH_CX")

# FTP — hospedagem temporária de vídeos para Instagram Stories
FTP_HOST   = os.getenv("FTP_HOST",   "ftp.cojanez.cnt.br")
FTP_USER   = os.getenv("FTP_USER",   "cojanez")
FTP_PASS   = os.getenv("FTP_PASS",   "")   # ← OBRIGATÓRIO no .env: FTP_PASS=sua_senha
FTP_PASTA  = os.getenv("FTP_PASTA",  "/Web/wilianjanez/movies/auto_post_vivendo")
FTP_URL    = os.getenv("FTP_URL",    "https://wilianjanez.inf.br/movies/auto_post_vivendo")
# Lista de imagens de fundo — separadas por vírgula no .env
# Exemplo: FUNDO_URLS=https://foto1.jpg,https://foto2.jpg,https://foto3.jpg
_FUNDOS_RAW = os.getenv("FUNDO_URLS", "")
FUNDO_URLS  = [u.strip() for u in _FUNDOS_RAW.split(",") if u.strip()]

# Listas de fundo temáticas para o Story de Clima (opcionais — fallback para FUNDO_URLS)
# Exemplo: FUNDO_SOL_URLS=https://foto_sol1.jpg,https://foto_sol2.jpg
FUNDO_CLIMA: dict[str, list[str]] = {
    "SOL":        [u.strip() for u in os.getenv("FUNDO_SOL_URLS",        "").split(",") if u.strip()],
    "CHUVA":      [u.strip() for u in os.getenv("FUNDO_CHUVA_URLS",      "").split(",") if u.strip()],
    "NUBLADO":    [u.strip() for u in os.getenv("FUNDO_NUBLADO_URLS",    "").split(",") if u.strip()],
    "TEMPESTADE": [u.strip() for u in os.getenv("FUNDO_TEMPESTADE_URLS", "").split(",") if u.strip()],
}

# Fontes na pasta /fonts do próprio projeto (independe do sistema operacional)
_BASE      = os.path.dirname(os.path.abspath(__file__))
FONT_BOLD  = os.getenv("FONT_BOLD_PATH",  os.path.join(_BASE, "fonts", "Poppins-Bold.ttf"))
MUSIC_PATH = os.getenv("MUSIC_PATH", os.path.join(_BASE, "music", "background_music.mp3"))
FONT_REG   = os.getenv("FONT_REG_PATH",   os.path.join(_BASE, "fonts", "DejaVuSans.ttf"))
FONT_EMOJI = os.getenv("FONT_EMOJI_PATH", os.path.join(_BASE, "fonts", "NotoColorEmoji.ttf"))

INSTAGRAM_API_BASE = "https://graph.instagram.com/v21.0"

HASHTAGS_OBRIGATORIAS = "#ubatuba #praiaubatuba #vivendoubatuba #ubatubahoje #ubatubasp #litoralnorte"

def _garantir_hashtags(hashtags: str) -> str:
    """Acrescenta as hashtags obrigatórias que ainda não estejam presentes."""
    existentes = set(hashtags.lower().split())
    adicionais = [h for h in HASHTAGS_OBRIGATORIAS.split() if h.lower() not in existentes]
    if adicionais:
        return hashtags.rstrip() + " " + " ".join(adicionais)
    return hashtags

# =============================================================================
# LOG
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("agente_ubatuba.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def _escolher_fundo_clima(condicao: str) -> str:
    """Retorna URL de fundo adequada à condição meteorológica.
    Usa a lista temática se configurada, caso contrário sorteia de FUNDO_URLS."""
    lista = FUNDO_CLIMA.get(condicao.upper(), [])
    if lista:
        url = random.choice(lista)
        log.info(f"🖼️  Fundo clima '{condicao}' — {lista.index(url)+1}/{len(lista)}: {url}")
        return url
    url = random.choice(FUNDO_URLS)
    log.info(f"🖼️  Fundo clima '{condicao}' sem lista específica — usando aleatório: {url}")
    return url


# =============================================================================
# PASSO 1: CAPTURA DE DADOS
# =============================================================================

def buscar_clima_openweather() -> str:
    """Busca clima atual + previsão do dia via OpenWeatherMap. Retorna bloco formatado ou ''."""
    if not OPENWEATHER_API_KEY:
        return ""
    log.info("🌤️  Buscando clima via OpenWeatherMap...")
    try:
        r_atual = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": "Ubatuba,BR", "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "pt_br"},
            timeout=15,
        )
        r_atual.raise_for_status()
        atual = r_atual.json()

        r_prev = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"q": "Ubatuba,BR", "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "pt_br", "cnt": 8},
            timeout=15,
        )
        r_prev.raise_for_status()
        previsao = r_prev.json()

        temp      = atual["main"]["temp"]
        temp_min  = atual["main"]["temp_min"]
        temp_max  = atual["main"]["temp_max"]
        sensacao  = atual["main"]["feels_like"]
        umidade   = atual["main"]["humidity"]
        descricao = atual["weather"][0]["description"]
        vento_kmh = round(atual["wind"]["speed"] * 3.6)

        proximas = []
        for item in previsao["list"][:4]:
            hora = datetime.fromtimestamp(item["dt"]).strftime("%Hh")
            t    = item["main"]["temp"]
            desc = item["weather"][0]["description"]
            proximas.append(f"  {hora}: {t:.0f}°C, {desc}")

        log.info(f"✅ OpenWeatherMap: {temp:.0f}°C, {descricao}")
        return (
            f"=== 🌤️ CLIMA ATUAL ===\n"
            f"  Temperatura: {temp:.0f}°C (sensação {sensacao:.0f}°C)\n"
            f"  Mín/Máx: {temp_min:.0f}°C / {temp_max:.0f}°C\n"
            f"  Condição: {descricao}\n"
            f"  Umidade: {umidade}%\n"
            f"  Vento: {vento_kmh} km/h\n\n"
            f"=== 🔮 PREVISÃO PRÓXIMAS HORAS ===\n"
            + "\n".join(proximas)
        )
    except requests.exceptions.RequestException as e:
        log.warning(f"⚠️  Erro OpenWeatherMap: {e}")
        return ""


def buscar_mar_open_meteo() -> str:
    """Busca condições do mar via Open-Meteo Marine API (gratuita, sem API key). Retorna bloco ou ''."""
    log.info("🏄 Buscando mar via Open-Meteo Marine...")
    try:
        r = requests.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params={
                "latitude":      -23.43,
                "longitude":     -45.08,
                "hourly":        "wave_height,wave_period",
                "timezone":      "America/Sao_Paulo",
                "forecast_days": 1,
            },
            timeout=15,
        )
        r.raise_for_status()
        hourly = r.json().get("hourly", {})

        times    = hourly.get("time", [])
        alturas  = hourly.get("wave_height", [])
        periodos = hourly.get("wave_period", [])

        agora  = datetime.now().hour
        linhas = []
        for i, t in enumerate(times):
            hora = int(t[11:13])
            if hora >= agora and len(linhas) < 4 and i < len(alturas) and alturas[i] is not None:
                per = periodos[i] if i < len(periodos) and periodos[i] is not None else None
                linhas.append(
                    f"  {hora:02d}h: ondas {alturas[i]:.1f}m, período {per:.0f}s"
                    if per else f"  {hora:02d}h: ondas {alturas[i]:.1f}m"
                )

        if not linhas:
            return ""

        log.info(f"✅ Open-Meteo Marine: {linhas[0].strip()}")
        return "=== 🏄 MAR & ONDAS ===\n" + "\n".join(linhas)

    except requests.exceptions.RequestException as e:
        log.warning(f"⚠️  Erro Open-Meteo Marine: {e}")
        return ""


def buscar_clima_apenas() -> str:
    """
    Busca dados de clima para o Story diário.
    Prioriza OpenWeatherMap + Open-Meteo Marine (sem consumir créditos Tavily).
    Fallback para Tavily se as APIs diretas falharem.
    """
    hoje     = datetime.now()
    data_br  = hoje.strftime("%d/%m/%Y")
    data_ext = hoje.strftime("%d de %B de %Y")

    log.info(f"🌤️  Buscando clima — {data_br}...")

    # APIs diretas — não consomem créditos Tavily
    bloco_clima = buscar_clima_openweather()
    bloco_mar   = buscar_mar_open_meteo()

    # Só pula o Tavily se o OpenWeatherMap retornou dados de temperatura/condição.
    # Apenas dados de ondas (Open-Meteo) não são suficientes para o Claude gerar
    # conteúdo de clima com confiança.
    if bloco_clima:
        blocos    = [b for b in [bloco_clima, bloco_mar] if b]
        cabecalho = (
            f"DATA DE HOJE: {data_br}\n"
            f"Use APENAS informações de clima e tempo.\n"
            f"{'='*60}\n"
        )
        return cabecalho + "\n\n".join(blocos)

    # Fallback: Tavily (busca clima; Open-Meteo Marine é adicionado se disponível)
    log.info("⚠️  OpenWeatherMap indisponível — tentando Tavily para dados de clima...")
    buscas_tavily = [("🌤️ CLIMA HOJE", f"Ubatuba previsão tempo temperatura chuva {data_ext}")]
    if not bloco_mar:
        buscas_tavily.append(("🏄 MAR & ONDAS", f"Ubatuba condições mar ondas vento {data_ext}"))

    blocos = []
    if bloco_mar:
        blocos.append(bloco_mar)   # inclui dados de ondas já obtidos

    for categoria, query in buscas_tavily:
        itens = _buscar_tavily(query, categoria, hoje, include_domains=FONTES_LOCAIS, days=1)
        if not itens:
            itens = _buscar_tavily(query, categoria, hoje, include_domains=None, days=1)
        if itens:
            blocos.append(f"=== {categoria} ===\n" + "\n".join(itens))
            log.info(f"    ✅ {categoria}: {len(itens)} resultado(s)")
        else:
            log.info(f"    ⚠️  {categoria}: sem resultados")
        time.sleep(1.0)

    if not blocos:
        return ""

    cabecalho = (
        f"DATA DE HOJE: {data_br}\n"
        f"Use APENAS informações de clima e tempo.\n"
        f"{'='*60}\n"
    )
    return cabecalho + "\n\n".join(blocos)


# Fontes locais de Ubatuba — priorizadas em TODAS as buscas
FONTES_LOCAIS = [
    "ubatubatimes.com.br",   # Jornal local online
    "ubatuba.sp.gov.br",     # Prefeitura de Ubatuba
]

# Feeds RSS das fontes locais — lidos diretamente, sem consumir API
RSS_FONTES_LOCAIS = [
    "https://ubatubatimes.com.br/feed/",
    "https://www.ubatuba.sp.gov.br/feed/",
]

def _buscar_tavily(query: str, categoria: str, hoje,
                   include_domains: list = None, days: int = 3) -> list:
    """
    Executa uma busca na Tavily e retorna lista de itens formatados.
    Se include_domains for passado, restringe a busca àqueles domínios.
    """
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "include_answer": True,
        "include_raw_content": False,
        "max_results": 5 if include_domains else 4,
        "days": days,
    }
    if include_domains:
        payload["include_domains"] = include_domains

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=25
        )
        resp.raise_for_status()
        dados = resp.json()
        itens = []

        if dados.get("answer"):
            itens.append(f"  Resumo: {dados['answer']}")

        for r in dados.get("results", []):
            titulo   = r.get("title", "").strip()
            conteudo = r.get("content", "")[:500].strip()
            pub      = r.get("published_date", "")
            url      = r.get("url", "")
            is_local = any(d in url for d in FONTES_LOCAIS)
            tag      = " 📍LOCAL" if is_local else ""
            idade    = ""
            if pub:
                try:
                    dp = datetime.fromisoformat(pub[:10])
                    d  = (hoje - dp).days
                    if d > 10:
                        continue
                    idade = "[HOJE]" if d == 0 else f"[{d}d atrás]"
                except ValueError:
                    idade = "[data desconhecida]"
            itens.append(f"  • {idade}{tag} {titulo}\n    {conteudo}")

        return itens

    except requests.exceptions.RequestException as e:
        log.warning(f"  ⚠️  Erro Tavily '{categoria}': {e}")
        return []


_HTML_RE = re.compile(r'<[^>]+>')

def _buscar_rss(feed_url: str, categoria: str, hoje, days: int = 7) -> list:
    """Lê feed RSS diretamente (sem API key) e retorna itens dos últimos `days` dias."""
    try:
        feed  = feedparser.parse(feed_url)
        itens = []
        for entry in feed.entries[:20]:
            pub = None
            for attr in ("published_parsed", "updated_parsed"):
                raw = getattr(entry, attr, None)
                if raw:
                    try:
                        pub = datetime(*raw[:6])
                        break
                    except Exception:
                        pass

            if pub:
                d = (hoje - pub).days
                if d > days:
                    continue
                idade = "[HOJE]" if d == 0 else f"[{d}d atrás]"
            else:
                idade = "[data desconhecida]"

            titulo = _HTML_RE.sub("", entry.get("title", "")).strip()
            resumo = _HTML_RE.sub("", entry.get("summary", ""))[:400].strip()
            itens.append(f"  • {idade} 📍LOCAL {titulo}\n    {resumo}")

        return itens
    except Exception as e:
        log.warning(f"  ⚠️  Erro RSS '{categoria}' ({feed_url}): {e}")
        return []


def _buscar_google(query: str, categoria: str, hoje, days: int = 3) -> list:
    """Busca via Google Custom Search API (100 req/dia grátis). Retorna lista de itens."""
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_CX:
        return []
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key":          GOOGLE_SEARCH_API_KEY,
                "cx":           GOOGLE_SEARCH_CX,
                "q":            query,
                "num":          5,
                "dateRestrict": f"d{max(1, days)}",
                "lr":           "lang_pt",
            },
            timeout=15,
        )
        resp.raise_for_status()
        itens = []
        for item in resp.json().get("items", []):
            titulo   = item.get("title", "").strip()
            snippet  = item.get("snippet", "")[:400].strip()
            url      = item.get("link", "")
            is_local = any(d in url for d in FONTES_LOCAIS)
            tag      = " 📍LOCAL" if is_local else ""
            itens.append(f"  •{tag} {titulo}\n    {snippet}")
        log.info(f"    ✅ Google '{categoria}': {len(itens)} resultado(s)")
        return itens
    except requests.exceptions.RequestException as e:
        log.warning(f"  ⚠️  Erro Google Search '{categoria}': {e}")
        return []


def buscar_noticias_ubatuba() -> str:
    """
    Busca notícias recentes sobre Ubatuba em duas etapas complementares:

    ETAPA 1 — Fontes locais (adicional):
        Busca em ubatubatimes.com.br e ubatuba.sp.gov.br para garantir
        que notícias hiperlocais entrem no contexto. Os resultados são
        adicionados ao pool geral — NÃO são priorizados sobre outros.

    ETAPA 2 — Busca geral por categoria (todas as fontes):
        8 categorias sem restrição de domínio. A IA decide o mais
        relevante considerando TODAS as fontes de forma igualitária.
    """
    hoje     = datetime.now()
    data_br  = hoje.strftime("%d/%m/%Y")
    data_ext = hoje.strftime("%d de %B de %Y")
    mes_ano  = hoje.strftime("%B de %Y")

    log.info(f"🔍 Buscando notícias — {data_br}...")
    log.info(f"   📍 Fontes locais incluídas: {', '.join(FONTES_LOCAIS)}")

    blocos = []

    # ── ETAPA 1: Fontes locais via RSS (sem API) ───────────────────────────────
    log.info("  📍 Etapa 1 — fontes locais via RSS...")
    itens_locais = []
    for feed_url in RSS_FONTES_LOCAIS:
        itens_locais.extend(_buscar_rss(feed_url, "LOCAL", hoje, days=7))

    if itens_locais:
        blocos.append("=== 📍 FONTES LOCAIS ===\n" + "\n".join(itens_locais[:8]))
        log.info(f"    ✅ RSS local: {len(itens_locais)} resultado(s)")
    else:
        log.info("  ⚠️  RSS sem resultados — tentando Tavily local...")
        for categoria, query in [
            ("📍 UBATUBA TIMES", f"Ubatuba notícias {mes_ano}"),
            ("📍 PREFEITURA",    f"Ubatuba prefeitura noticias eventos {mes_ano}"),
        ]:
            itens = _buscar_tavily(query, categoria, hoje, include_domains=FONTES_LOCAIS, days=7)
            if itens:
                blocos.append(f"=== {categoria} ===\n" + "\n".join(itens))
                log.info(f"    ✅ {categoria}: {len(itens)} resultado(s)")
            time.sleep(1.2)

    # ── ETAPA 2: Busca geral — Google → Tavily fallback ───────────────────────
    log.info("  🌐 Etapa 2 — busca geral (Google → Tavily fallback)...")
    buscas_gerais = {
        "🌤️ CLIMA & TEMPO": f"Ubatuba previsão tempo temperatura chuva {data_ext}",
        "🏖️ PRAIAS":        f"Ubatuba praias condições mar bandeira qualidade água {data_ext}",
        "🎭 EVENTOS":        f"Ubatuba eventos shows festas feiras programação {mes_ano}",
        "🍤 GASTRONOMIA":   f"Ubatuba restaurantes gastronomia frutos do mar novidades {mes_ano}",
        "🌿 NATUREZA":      f"Ubatuba trilhas parques cachoeiras ecoturismo natureza {mes_ano}",
        "🏄 SURF & MAR":    f"Ubatuba surf ondas vento maré previsão mar {data_ext}",
        "🎨 CULTURA":       f"Ubatuba cultura arte artesanato tradição caiçara {mes_ano}",
        "✈️ TURISMO":       f"Ubatuba turismo atrações roteiros pontos turísticos {mes_ano}",
    }
    for categoria, query in buscas_gerais.items():
        itens = _buscar_google(query, categoria, hoje, days=3)
        if not itens:
            itens = _buscar_tavily(query, categoria, hoje, include_domains=None, days=3)
        if itens:
            blocos.append(f"=== {categoria} ===\n" + "\n".join(itens))
            log.info(f"    ✅ {categoria}: {len(itens)} resultado(s)")
        else:
            log.info(f"    ⚠️  {categoria}: sem resultados")
        time.sleep(1.2)

    if not blocos:
        log.error("❌ Nenhuma notícia encontrada.")
        return ""

    cabecalho = (
        f"DATA DE HOJE: {data_br}\n"
        f"Use APENAS informações compatíveis com a data de hoje.\n"
        f"Resultados de {', '.join(FONTES_LOCAIS)} estão incluídos mas\n"
        f"a relevância deve ser decidida pelo conteúdo, não pela fonte.\n"
        f"{'='*60}\n"
    )
    log.info(f"  ✅ Busca concluída: {len(blocos)} blocos.")
    return cabecalho + "\n\n".join(blocos)


# =============================================================================
# PROMPTS DA IA
# =============================================================================

# Prompt 1 — Story de Clima/Tempo (todo dia, busca focada só em tempo)
PROMPT_TEMPO = """
Você é o curador do perfil "Vivendo em Ubatuba" no Instagram.

TAREFA: Gere conteúdo APENAS sobre clima e tempo em Ubatuba para hoje.
DATA: Use APENAS informações compatíveis com a data de hoje. Se não houver: PULAR
FILTRAGEM: Nada de política, crimes ou tragédias. Se não houver dados de clima: PULAR
FONTES LOCAIS: Prefira resultados marcados com 📍LOCAL.

SAÍDA — JSON puro sem markdown:
{
  "condicao": "SOL | CHUVA | NUBLADO | TEMPESTADE | VARIAVEL",
  "confianca": "ALTA | MEDIA | BAIXA",
  "titulo": "frase impacto com 1 emoji de clima — MÁXIMO 4 PALAVRAS — ex: '☀️ Dia lindo hoje!'",
  "subtitulo": "temperatura + condição resumida — MÁXIMO 10 PALAVRAS",
  "temperaturas": "linha curta com mín e máx — ex: '🌡️ Mín: 22°C | Máx: 29°C' — se não houver dados: null",
  "corpo": "2-3 frases sobre o tempo do dia, previsão e dica de praia. Tom leve e nativo.",
  "cta": "pergunta sobre o que as pessoas vão fazer com esse tempo hoje",
  "hashtags": "#ubatuba #vivendoubatuba #tempohoje #praiasubatuba #litoralnorte"
}
REGRA condicao: escolha UMA — SOL (ensolarado/quente), CHUVA (chuva leve/moderada), NUBLADO (nuvens sem chuva), TEMPESTADE (temporal/chuva forte/trovões), VARIAVEL (parcialmente nublado/incerto).
TOM: animado, leve, como um amigo que mora na cidade.
"""

# Prompt 2 — Post temático (top 5 notícias do dia — seg a qui, sáb e dom)
PROMPT_TEMATICO = """
Você é o curador do perfil "Vivendo em Ubatuba" no Instagram.

MISSÃO: Analisar TODOS os dados e listar OS 5 CONTEÚDOS DE MAIOR IMPACTO do dia, do mais ao menos relevante.

FILTRAGEM: Nada de política, crimes ou tragédias — responda PULAR se só houver isso.
DATA: Use APENAS informações compatíveis com a data de hoje. Se tudo parecer antigo: PULAR
FONTES LOCAIS: Resultados de ubatubatimes.com.br e ubatuba.sp.gov.br podem estar incluídos.
Avalie-os pelo CONTEÚDO, não pela fonte — a relevância é o único critério.

CRITÉRIO DE SELEÇÃO (avalie cada candidato considerando):
1. URGÊNCIA: acontece hoje ou nos próximos dias?
2. IMPACTO: afeta ou interessa muita gente?
3. EXCLUSIVIDADE: é algo que as pessoas não saberiam sem ver o post?
4. ENGAJAMENTO: gera comentários, compartilhamentos, identificação?

TEMAS DISPONÍVEIS: PRAIAS | EVENTOS | GASTRONOMIA | NATUREZA | TURISMO | SURF | CULTURA

HASHTAGS POR TEMA:
- PRAIAS:      #ubatuba #praiasubatuba #vivendoubatuba #litoralnorte #ubatubacity
- EVENTOS:     #ubatuba #eventosubatuba #vivendoubatuba #litoralnorte #agendaubatuba
- GASTRONOMIA: #ubatuba #gastronomialocal #vivendoubatuba #comidalitoranea #frutosdomar
- NATUREZA:    #ubatuba #naturezaubatuba #vivendoubatuba #ecoturismo #mataatlantica
- TURISMO:     #ubatuba #turismobrasil #vivendoubatuba #litoralnorte #destinoubatuba
- SURF:        #ubatuba #surfubatuba #vivendoubatuba #ondas #surfe
- CULTURA:     #ubatuba #culturacaicara #vivendoubatuba #tradicaocaicara #litoralnorte

SAÍDA — JSON puro sem markdown:
{
  "confianca": "ALTA | MEDIA | BAIXA",
  "candidatos": [
    {
      "posicao": 1,
      "tema": "PRAIAS | EVENTOS | GASTRONOMIA | NATUREZA | TURISMO | SURF | CULTURA",
      "motivo_escolha": "1 frase explicando por que este conteúdo é relevante hoje",
      "titulo": "frase impacto com 1-2 emojis — MÁXIMO 4 PALAVRAS — vai enorme na imagem",
      "subtitulo": "dado-chave — MÁXIMO 10 PALAVRAS — vai menor na imagem",
      "corpo": "3-4 frases completas para a legenda. Tom nativo, leve, com dica prática local.",
      "cta": "pergunta curta e aberta para engajar comentários",
      "hashtags": "use as hashtags do tema escolhido"
    }
  ]
}
REGRAS: sempre 5 candidatos (posicao 1 a 5). Se não houver 5 notícias distintas: repita temas com ângulos diferentes.
TOM: nativo da cidade, leve, positivo, como quem mora lá.
"""

# Prompt 3 — Resumo da Semana (toda sexta-feira)
PROMPT_RESUMO_SEMANA = """
Você é o curador do perfil "Vivendo em Ubatuba" no Instagram.

TAREFA: Criar o "Resumo da Semana" com as notícias mais relevantes dos últimos 7 dias.

FILTRAGEM: Nada de política, crimes ou tragédias.
FONTES LOCAIS: Resultados de sites locais podem estar incluídos — avalie pelo conteúdo e relevância.

CRITÉRIO DE SELEÇÃO:
- Selecione entre 5 e 10 notícias/fatos relevantes da semana
- Priorize: eventos, praias, gastronomia, cultura, natureza, turismo, surf
- Cada item deve ser curtíssimo — máximo 8 palavras
- Varie os temas (não coloque só praias ou só eventos)

SAÍDA — JSON puro sem markdown:
{
  "confianca": "ALTA | MEDIA | BAIXA",
  "itens": [
    {"emoji": "🌊", "texto": "resumo curtíssimo — máx 8 palavras"},
    {"emoji": "🎭", "texto": "resumo curtíssimo — máx 8 palavras"}
  ],
  "corpo": "2-3 frases introdutórias resumindo como foi a semana. Tom leve e nativo.",
  "cta": "pergunta engajadora sobre a semana ou o fim de semana que vem",
  "hashtags": "#ubatuba #vivendoubatuba #resumodasemana #litoralnorte #ubatubacity"
}
REGRAS: mínimo 5, máximo 10 itens. Se não houver notícias suficientes: PULAR
TOM: leve, positivo, como um amigo contando o que rolou na cidade.
"""


def _chamar_claude(system_prompt: str, user_msg: str, label: str, max_tokens: int = 1024) -> dict | str:
    """Chama a API do Claude e retorna dict com o JSON ou 'PULAR'."""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-opus-4-5",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=60
        )
        resp.raise_for_status()
        texto = resp.json()["content"][0]["text"].strip()

        if texto.upper() == "PULAR":
            log.info(f"⏭️  Claude [{label}]: sem conteúdo confiável.")
            return "PULAR"

        conteudo  = json.loads(texto.replace("```json","").replace("```","").strip())
        confianca = conteudo.get("confianca", "?")
        log.info(f"✅ [{label}] gerado — Confiança: {confianca}")

        if confianca == "BAIXA":
            log.warning(f"⚠️  [{label}] Confiança BAIXA — pulando.")
            return "PULAR"

        return conteudo

    except json.JSONDecodeError as e:
        log.error(f"❌ JSON inválido [{label}]: {e}")
        raise
    except requests.exceptions.RequestException as e:
        log.error(f"❌ Erro Anthropic [{label}]: {e}")
        raise


def gerar_conteudo_clima(noticias: str) -> dict | str:
    """Gera conteúdo SEMPRE de Clima/Tempo para o Story fixo."""
    if not noticias.strip():
        return "PULAR"
    log.info("🌤️  Gerando Story de Clima...")
    return _chamar_claude(
        PROMPT_TEMPO,
        "Dados coletados:\n\n" + noticias + "\n\nGere conteúdo APENAS sobre clima e tempo.",
        "CLIMA"
    )


def gerar_conteudo_tematico(noticias: str) -> dict | str:
    """
    Analisa TODOS os dados coletados e monta um top 5 de conteúdos relevantes.
    Sorteia aleatoriamente um dos 5 para publicar — evita repetição ao longo dos dias.
    """
    if not noticias.strip():
        return "PULAR"

    log.info("📌 Gerando top 5 de conteúdos do dia...")
    resultado = _chamar_claude(
        PROMPT_TEMATICO,
        "Dados coletados de TODOS os temas:\n\n" + noticias +
        "\n\nAnalise tudo acima e liste OS 5 CONTEÚDOS DE MAIOR IMPACTO para o público hoje.",
        "TOP 5",
        max_tokens=3000,
    )

    if resultado == "PULAR":
        return "PULAR"

    candidatos = resultado.get("candidatos", [])
    if not candidatos:
        log.error("❌ Top 5 retornou lista vazia.")
        return "PULAR"

    escolhido = random.choice(candidatos)
    log.info(f"🎲 Sorteado {escolhido.get('posicao','?')}/{len(candidatos)}: [{escolhido.get('tema','?')}] {escolhido.get('titulo','?')}")
    return escolhido


# =============================================================================
# PASSO 3: GERAÇÃO DE IMAGEM
# =============================================================================

_EMOJI_RE = re.compile(
    r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002702-\U000027B0\U0001F000-\U0001F02F]+',
    re.UNICODE
)

def _load_fonts():
    """Carrega as fontes da pasta /fonts do projeto."""
    try:
        fe = ImageFont.truetype(FONT_EMOJI, 109)  # NotoColorEmoji só aceita 109px
    except OSError:
        log.error("❌ NotoColorEmoji não encontrada em: " + FONT_EMOJI)
        log.error("   Certifique-se de que a pasta fonts/ está na mesma pasta do script.")
        fe = None
    try:
        fb_96  = ImageFont.truetype(FONT_BOLD, 96)
        fb_108 = ImageFont.truetype(FONT_BOLD, 108)
        fb_32  = ImageFont.truetype(FONT_BOLD, 32)
        fb_30  = ImageFont.truetype(FONT_BOLD, 30)
        fr_48  = ImageFont.truetype(FONT_REG,  48)
        fr_54  = ImageFont.truetype(FONT_REG,  54)
    except OSError:
        log.error("❌ Poppins-Bold ou DejaVuSans não encontradas em: " + _BASE + "/fonts/")
        fb_96 = fb_108 = fb_32 = fb_30 = fr_48 = fr_54 = ImageFont.load_default()
    return fe, fb_96, fb_108, fb_32, fb_30, fr_48, fr_54

def _render_emoji(fe, char: str, target_h: int) -> Image.Image:
    """Renderiza emoji em 109px e redimensiona para target_h."""
    if fe is None:
        return Image.new("RGBA", (target_h, target_h), (0,0,0,0))
    tmp = Image.new("RGBA", (300, 200), (0,0,0,0))
    d   = ImageDraw.Draw(tmp)
    bb  = d.textbbox((0,0), char, font=fe, embedded_color=True)
    w, h = bb[2]-bb[0], bb[3]-bb[1]
    if w <= 0 or h <= 0:
        return Image.new("RGBA", (target_h, target_h), (0,0,0,0))
    canvas = Image.new("RGBA", (w+4, h+4), (0,0,0,0))
    dc = ImageDraw.Draw(canvas)
    dc.text((-bb[0]+2, -bb[1]+2), char, font=fe, embedded_color=True)
    scale = target_h / max(w, h)
    return canvas.resize((max(1,int(w*scale)), max(1,int(h*scale))), Image.LANCZOS)

def _split(text: str):
    parts, last = [], 0
    for m in _EMOJI_RE.finditer(text):
        if m.start() > last: parts.append((text[last:m.start()], False))
        parts.append((m.group(), True))
        last = m.end()
    if last < len(text): parts.append((text[last:], False))
    return [(p,e) for p,e in parts if p]

def _measure(draw, fe, text, font, emoji_h):
    x = 0
    for part, is_emoji in _split(text):
        if is_emoji: x += _render_emoji(fe, part, emoji_h).width + 6
        else:
            bb = draw.textbbox((0,0), part, font=font)
            x += bb[2]-bb[0]
    return x

def _wrap(draw, fe, text, font, emoji_h, max_w):
    words = text.split(' ')
    lines, cur = [], ''
    for w in words:
        test = (cur + ' ' + w).strip()
        if _measure(draw, fe, test, font, emoji_h) <= max_w: cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def _draw_mixed(img, draw, fe, pos, text, font, fill, emoji_h, shadow=True):
    x, y = pos
    bb_ref = draw.textbbox((0,0), "Hg", font=font)
    th = bb_ref[3]-bb_ref[1]
    for part, is_emoji in _split(text):
        if is_emoji:
            ei = _render_emoji(fe, part, emoji_h)
            ey = y + max(0, (th-ei.height)//2)
            if shadow:
                sh = Image.new("RGBA", ei.size, (0,0,0,0))
                for px in range(ei.width):
                    for py in range(ei.height):
                        r,g,b,a = ei.getpixel((px,py))
                        sh.putpixel((px,py),(0,0,0,a//2))
                img.paste(sh, (x+4,ey+4), sh)
            img.paste(ei, (x,ey), ei)
            x += ei.width + 6
        else:
            if shadow:
                # Sombra em múltiplas direções — legibilidade sem fundo escuro
                for dx,dy in [(2,2),(3,3),(4,4),(3,1),(1,3),(-1,3),(3,-1)]:
                    draw.text((x+dx,y+dy), part, font=font, fill=(0,0,0,220))
            draw.text((x,y), part, font=font, fill=fill)
            bb = draw.textbbox((0,0), part, font=font)
            x += bb[2]-bb[0]

def _baixar_fundo(url, W, H):
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        fundo = Image.open(io.BytesIO(r.content)).convert("RGB")
        ratio = max(W/fundo.width, H/fundo.height)
        nw, nh = int(fundo.width*ratio), int(fundo.height*ratio)
        fundo = fundo.resize((nw, nh), Image.LANCZOS)
        return fundo.crop(((nw-W)//2, (nh-H)//2, (nw-W)//2+W, (nh-H)//2+H))
    except Exception as e:
        log.warning(f"⚠️  Erro ao baixar fundo: {e}. Usando gradiente.")
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        for y in range(H):
            t = y/H
            d.line([(0,y),(W,y)], fill=(int(10+20*t), int(40+50*t), int(80+20*t)))
        return img

def buscar_noticias_semana() -> str:
    """
    Busca notícias dos últimos 7 dias para o Resumo da Semana (sexta-feira).
    Usa janela maior e prioriza fontes locais.
    """
    hoje    = datetime.now()
    data_br = hoje.strftime("%d/%m/%Y")
    mes_ano = hoje.strftime("%B de %Y")

    log.info("📋 Buscando notícias da semana (últimos 7 dias)...")

    # Busca complementar nas fontes locais
    buscas_locais_semana = [
        ("📍 LOCAL SEMANA", f"Ubatuba notícias semana {mes_ano}"),
    ]
    buscas_gerais_semana = [
        ("🏖️ PRAIAS SEMANA", f"Ubatuba praias mar condições semana {mes_ano}"),
        ("🎭 EVENTOS SEMANA", f"Ubatuba eventos shows festas {mes_ano}"),
        ("🍤 GASTRO SEMANA",  f"Ubatuba gastronomia restaurantes novidades {mes_ano}"),
        ("🌿 NATURE SEMANA",  f"Ubatuba natureza trilhas turismo {mes_ano}"),
        ("🎨 CULTURA SEMANA", f"Ubatuba cultura arte caiçara {mes_ano}"),
    ]

    blocos = []

    # Fontes locais via RSS (sem API), fallback Tavily
    log.info("  📍 RSS fontes locais (semana)...")
    itens_locais = []
    for feed_url in RSS_FONTES_LOCAIS:
        itens_locais.extend(_buscar_rss(feed_url, "LOCAL SEMANA", hoje, days=7))

    if itens_locais:
        blocos.append("=== 📍 LOCAL SEMANA ===\n" + "\n".join(itens_locais[:10]))
        log.info(f"    ✅ RSS local semana: {len(itens_locais)} resultado(s)")
    else:
        log.info("  ⚠️  RSS sem resultados — tentando Tavily local...")
        for categoria, query in buscas_locais_semana:
            itens = _buscar_tavily(query, categoria, hoje, include_domains=FONTES_LOCAIS, days=7)
            if itens:
                blocos.append(f"=== {categoria} ===\n" + "\n".join(itens))
                log.info(f"    ✅ {categoria}: {len(itens)} resultado(s)")
            time.sleep(1.2)

    # Busca geral — Google → Tavily fallback
    log.info("  🌐 Busca geral semana (Google → Tavily fallback)...")
    for categoria, query in buscas_gerais_semana:
        itens = _buscar_google(query, categoria, hoje, days=7)
        if not itens:
            itens = _buscar_tavily(query, categoria, hoje, include_domains=None, days=7)
        if itens:
            blocos.append(f"=== {categoria} ===\n" + "\n".join(itens))
            log.info(f"    ✅ {categoria}: {len(itens)} resultado(s)")
        time.sleep(1.2)

    if not blocos:
        return ""

    cabecalho = (
        f"DATA DE HOJE: {data_br} (SEXTA-FEIRA — RESUMO DA SEMANA)\n"
        f"Selecione as notícias mais relevantes dos últimos 7 dias.\n"
        f"A relevância deve ser decidida pelo conteúdo, não pela fonte.\n"
        f"{'='*60}\n"
    )
    log.info(f"  ✅ Semana: {len(blocos)} blocos coletados.")
    return cabecalho + "\n\n".join(blocos)


def gerar_resumo_semana(noticias: str) -> dict | str:
    """Gera o Resumo da Semana com 5-10 notícias relevantes."""
    if not noticias.strip():
        return "PULAR"
    log.info("📋 Gerando Resumo da Semana com Claude...")
    return _chamar_claude(
        PROMPT_RESUMO_SEMANA,
        "Notícias dos últimos 7 dias:\n\n" + noticias +
        "\n\nSelecione as 5-10 mais relevantes para o Resumo da Semana.",
        "RESUMO SEMANA"
    )


def gerar_card(titulo: str, subtitulo: str, fundo_url: str, tamanho: tuple) -> bytes:
    """
    Gera card com:
    - Foto de fundo de Ubatuba
    - Metade inferior com fundo preto sólido (máxima legibilidade)
    - Título GRANDE com emoji colorido real
    - Subtítulo menor
    - CTA no rodapé
    """
    W, H = tamanho
    M    = 64

    fe, fb_96, fb_108, fb_32, fb_30, fr_48, fr_54 = _load_fonts()
    f_tit = fb_96  if H <= 1080 else fb_108
    f_sub = fr_48  if H <= 1080 else fr_54
    f_cta = fb_30
    f_mrc = fb_32

    eh_tit = 88  if H <= 1080 else 100
    eh_sub = 44
    eh_cta = 28

    # Fundo
    fundo = _baixar_fundo(fundo_url, W, H)
    img   = fundo.convert("RGBA")

    # Opção C: foto 100% visível — só gradiente mínimo no topo para a marca
    tg  = Image.new("RGBA",(W,H),(0,0,0,0))
    dtg = ImageDraw.Draw(tg)
    for y in range(70):
        dtg.line([(0,y),(W,y)], fill=(0,0,0,int(120*(1-y/70))))
    img = Image.alpha_composite(img, tg)

    draw = ImageDraw.Draw(img)
    area = W - M*2

    # Marca no topo
    draw.text((M, 26), "VIVENDO EM UBATUBA", font=f_mrc, fill=(255,255,255,220))

    # Quebra linhas (até 3 linhas no título)
    linhas_tit = _wrap(draw, fe, titulo,    f_tit, eh_tit, area)[:3]
    linhas_sub = _wrap(draw, fe, subtitulo, f_sub, eh_sub, area)[:2]

    h_tit = 118 if H <= 1080 else 130
    h_sub = 66

    # Posiciona texto nos 40% inferiores
    y = int(H * 0.56)

    for linha in linhas_tit:
        _draw_mixed(img, draw, fe, (M,y), linha, f_tit, "white", eh_tit, shadow=True)
        y += h_tit

    y += 16
    draw.line([(M,y),(M+90,y)], fill=(255,255,255,180), width=4)
    y += 26

    for linha in linhas_sub:
        _draw_mixed(img, draw, fe, (M,y), linha, f_sub, (230,245,255), eh_sub, shadow=True)
        y += h_sub

    rodape_y = H - 65
    draw.line([(M,rodape_y-20),(W-M,rodape_y-20)], fill=(255,255,255,50), width=1)
    _draw_mixed(img, draw, fe, (M,rodape_y),
                "Leia a legenda completa 👇", f_cta, (200,225,255), eh_cta, shadow=False)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=96)
    return buf.getvalue()


# =============================================================================
# PASSO 4: UPLOAD IMGBB
# =============================================================================

def gerar_card_resumo(itens: list, fundo_url: str, tamanho: tuple) -> bytes:
    """
    Gera card especial para o Resumo da Semana (sexta-feira).

    Layout Opção A:
    ┌─────────────────────────────┐
    │ VIVENDO EM UBATUBA          │ ← marca topo
    │         [foto]              │
    │ 📋 Resumo da Semana         │ ← título fixo grande
    │ ─────────────────────       │ ← separador
    │ 🌊 Praias com bandeira verde │ ← itens (5-10)
    │ 🎭 Show no Sesc este fim... │
    │ 🍤 Festival de frutos do mar│
    │ + mais na legenda 👇        │ ← rodapé
    └─────────────────────────────┘
    """
    W, H = tamanho
    M    = 64

    fe, fb_96, fb_108, fb_32, fb_30, fr_48, fr_54 = _load_fonts()

    # Fontes específicas para o card de resumo
    try:
        f_titulo = ImageFont.truetype(FONT_BOLD, 72 if H <= 1080 else 82)
        f_item   = ImageFont.truetype(FONT_REG,  36 if H <= 1080 else 40)
        f_mrc    = ImageFont.truetype(FONT_BOLD, 32)
        f_cta    = ImageFont.truetype(FONT_BOLD, 28)
    except OSError:
        f_titulo = f_item = f_mrc = f_cta = ImageFont.load_default()

    eh_titulo = 66 if H <= 1080 else 76
    eh_item   = 32
    eh_cta    = 26

    # Fundo
    fundo = _baixar_fundo(fundo_url, W, H)
    img   = fundo.convert("RGBA")

    # Gradiente inferior — cobre 58% da imagem para acomodar lista de itens
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dg   = ImageDraw.Draw(grad)
    ini  = int(H * 0.38)
    for y in range(ini, H):
        p = (y - ini) / (H - ini)
        a = int(248 * (p ** 0.7))
        dg.line([(0, y), (W, y)], fill=(0, 0, 0, min(a, 248)))
    img = Image.alpha_composite(img, grad)

    # Gradiente topo
    tg  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dtg = ImageDraw.Draw(tg)
    for y in range(70):
        dtg.line([(0, y), (W, y)], fill=(0, 0, 0, int(120 * (1 - y / 70))))
    img = Image.alpha_composite(img, tg)

    draw = ImageDraw.Draw(img)
    area = W - M * 2

    # Marca topo
    draw.text((M, 26), "VIVENDO EM UBATUBA", font=f_mrc, fill=(255, 255, 255, 220))

    # Calcula alturas para posicionar o bloco
    h_titulo   = 88 if H <= 1080 else 100
    h_sep      = 28
    h_item_ln  = 48 if H <= 1080 else 54
    n_itens    = min(len(itens), 10)
    rodape_y   = H - 65

    total = h_titulo + h_sep + (n_itens * h_item_ln) + 20
    y = rodape_y - total - 20

    # Título fixo "📋 Resumo da Semana"
    titulo_txt = "📋 Resumo da Semana"
    _draw_mixed(img, draw, fe, (M, y), titulo_txt, f_titulo, "white", eh_titulo, shadow=True)
    y += h_titulo

    # Separador
    draw.line([(M, y), (W - M, y)], fill=(255, 255, 255, 80), width=2)
    y += h_sep

    # Itens da lista
    for item in itens[:n_itens]:
        emoji = item.get("emoji", "•")
        texto = item.get("texto", "")
        linha = f"{emoji} {texto}"
        # Trunca se muito longo
        while _measure(draw, fe, linha, f_item, eh_item) > area and len(linha) > 10:
            linha = linha[:-4] + "..."
        _draw_mixed(img, draw, fe, (M, y), linha, f_item, (220, 240, 255), eh_item, shadow=True)
        y += h_item_ln

    # Rodapé
    draw.line([(M, rodape_y - 20), (W - M, rodape_y - 20)], fill=(255, 255, 255, 40), width=1)
    _draw_mixed(img, draw, fe, (M, rodape_y),
                "Detalhes na legenda 👇", f_cta, (200, 225, 255), eh_cta, shadow=False)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=96)
    return buf.getvalue()


def fazer_upload_imgbb(imagem_bytes: bytes, nome: str) -> str:
    log.info(f"☁️  Upload '{nome}' → ImgBB...")
    try:
        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={
                "key": IMGBB_API_KEY,
                "image": base64.b64encode(imagem_bytes).decode("utf-8"),
                "name": nome,
                "expiration": 86400,
            },
            timeout=30
        )
        resp.raise_for_status()
        url = resp.json()["data"]["url"]
        log.info(f"✅ Upload OK: {url}")
        return url
    except requests.exceptions.RequestException as e:
        log.error(f"❌ Erro ImgBB: {e}")
        raise


# =============================================================================
# PASSO 5: PUBLICAÇÃO INSTAGRAM
# =============================================================================

def _aguardar_processamento_video(container_id: str,
                                   tentativas: int = 24,
                                   intervalo: int = 15) -> bool:
    """
    Consulta o status do container de vídeo até ficar FINISHED.
    Tenta até `tentativas` vezes com `intervalo` segundos entre cada uma.
    Retorna True se pronto, False se expirou ou deu erro.
    """
    endpoint = f"{INSTAGRAM_API_BASE}/{container_id}"
    for i in range(1, tentativas + 1):
        try:
            resp = requests.get(
                endpoint,
                params={"fields": "status_code,status", "access_token": IG_ACCESS_TOKEN},
                timeout=15
            )
            resp.raise_for_status()
            dados        = resp.json()
            status_code  = dados.get("status_code", "")
            status_msg   = dados.get("status", "")
            log.info(f"   ⏳ [{i}/{tentativas}] Status vídeo: {status_code} — {status_msg}")

            if status_code == "FINISHED":
                log.info("   ✅ Vídeo processado pelo Instagram!")
                return True
            if status_code == "ERROR":
                log.error(f"   ❌ Instagram recusou o vídeo: {status_msg}")
                return False

            time.sleep(intervalo)
        except Exception as e:
            log.warning(f"   ⚠️  Erro ao verificar status ({i}/{tentativas}): {e}")
            time.sleep(intervalo)

    log.error(f"   ❌ Timeout: vídeo não ficou FINISHED após {tentativas} tentativas.")
    return False


def _criar_container_video(video_url: str, is_story: bool = True) -> str:
    """
    Cria container de VÍDEO na API Graph do Instagram para Stories em vídeo.
    Aguarda o status FINISHED antes de retornar (evita erro 400 / subcode 2207027).
    Tenta até 3 vezes em caso de erro transitório (is_transient=true).
    """
    log.info("📦 Criando container de vídeo (STORY)...")
    endpoint = f"{INSTAGRAM_API_BASE}/{IG_USER_ID}/media"
    payload  = {
        "video_url":    video_url,
        "media_type":   "STORIES",
        "access_token": IG_ACCESS_TOKEN,
    }
    max_tentativas = 3
    for tentativa in range(1, max_tentativas + 1):
        try:
            resp = requests.post(endpoint, data=payload, timeout=30)
            resp.raise_for_status()
            cid = resp.json().get("id")
            if not cid:
                raise ValueError(f"Sem ID: {resp.json()}")
            log.info(f"✅ Container vídeo criado: {cid} — aguardando processamento...")

            pronto = _aguardar_processamento_video(cid)
            if not pronto:
                raise RuntimeError(f"Vídeo {cid} não ficou pronto para publicação.")

            return cid

        except requests.exceptions.HTTPError as e:
            log.error(f"❌ Erro container vídeo ({tentativa}/{max_tentativas}): "
                      f"{e.response.status_code} — {e.response.text[:200]}")
            if e.response.status_code >= 500 and tentativa < max_tentativas:
                espera = 30 * tentativa
                log.info(f"⏳ Erro {e.response.status_code} (servidor) — aguardando {espera}s...")
                time.sleep(espera)
            else:
                raise


def _criar_container(imagem_url, legenda="", is_story=False):
    tipo = "STORY" if is_story else "FEED"
    log.info(f"📦 Criando container {tipo}...")
    payload = {"image_url": imagem_url, "access_token": IG_ACCESS_TOKEN}
    if is_story: payload["media_type"] = "STORIES"
    else: payload["caption"] = legenda
    max_tentativas = 3
    for tentativa in range(1, max_tentativas + 1):
        try:
            resp = requests.post(f"{INSTAGRAM_API_BASE}/{IG_USER_ID}/media",
                                 data=payload, timeout=30)
            resp.raise_for_status()
            cid = resp.json().get("id")
            if not cid: raise ValueError(f"Sem ID: {resp.json()}")
            log.info(f"✅ Container {tipo}: {cid}")
            return cid
        except requests.exceptions.HTTPError as e:
            log.error(f"❌ Erro container {tipo} ({tentativa}/{max_tentativas}): "
                      f"{e.response.status_code} — {e.response.text[:200]}")
            if e.response.status_code >= 500 and tentativa < max_tentativas:
                espera = 30 * tentativa
                log.info(f"⏳ Erro {e.response.status_code} (servidor) — aguardando {espera}s...")
                time.sleep(espera)
            else:
                raise

def _publicar_container(container_id, tipo="POST"):
    log.info(f"🚀 Publicando {tipo}...")
    time.sleep(5)
    try:
        resp = requests.post(
            f"{INSTAGRAM_API_BASE}/{IG_USER_ID}/media_publish",
            data={"creation_id": container_id, "access_token": IG_ACCESS_TOKEN},
            timeout=30
        )
        resp.raise_for_status()
        dados = resp.json()
        log.info(f"🎉 {tipo} publicado! ID: {dados.get('id')}")
        return dados
    except requests.exceptions.HTTPError as e:
        log.error(f"❌ Erro publicar {tipo}: {e.response.status_code} — {e.response.text}")
        raise

def publicar_feed_e_stories(legenda, url_feed, url_story):
    resultados = {}
    try:
        cid = _criar_container(url_feed, legenda, is_story=False)
        resultados["post_id"] = _publicar_container(cid, "FEED").get("id")
    except Exception as e:
        log.error(f"❌ Feed falhou: {e}")
        resultados["post_id"] = None
    time.sleep(8)
    try:
        cid = _criar_container(url_story, is_story=True)
        resultados["story_id"] = _publicar_container(cid, "STORY").get("id")
    except Exception as e:
        log.error(f"❌ Story falhou: {e}")
        resultados["story_id"] = None
    return resultados


# =============================================================================
# ORQUESTRADOR
# =============================================================================

# =============================================================================
# YOUTUBE SHORTS — Geração de vídeo e publicação
# =============================================================================

def gerar_video_short(imagem_bytes: bytes, duracao: int = 10) -> bytes:
    """
    Converte um card JPEG em vídeo MP4 vertical (1080x1920) para YouTube Shorts.
    Adiciona música de fundo se o arquivo existir em music/background_music.mp3.

    Args:
        imagem_bytes: Bytes da imagem JPEG do card gerado.
        duracao:      Duração do vídeo em segundos (padrão: 10s).

    Retorna:
        bytes: Vídeo MP4 pronto para upload.
    """
    import tempfile
    import numpy as np
    from moviepy.editor import ImageClip, AudioFileClip, CompositeAudioClip

    log.info(f"🎬 Gerando vídeo Short ({duracao}s)...")

    # Converte bytes da imagem para array numpy
    from PIL import Image as PILImage
    img = PILImage.open(io.BytesIO(imagem_bytes)).convert("RGB")
    # Garante resolução 1080x1920 (Stories/Shorts)
    if img.size != (1080, 1920):
        img = img.resize((1080, 1920), PILImage.LANCZOS)
    img_array = np.array(img)

    # Cria clip de imagem estática
    clip = ImageClip(img_array, duration=duracao).set_fps(24)

    # Adiciona música de fundo se disponível
    if os.path.exists(MUSIC_PATH):
        try:
            audio = AudioFileClip(MUSIC_PATH)
            # Recorta o áudio para a duração do vídeo
            if audio.duration > duracao:
                audio = audio.subclip(0, duracao)
            # Fade in e fade out suaves
            audio = audio.audio_fadein(0.5).audio_fadeout(1.0)
            clip = clip.set_audio(audio)
            log.info(f"🎵 Música adicionada: {MUSIC_PATH}")
        except Exception as e:
            log.warning(f"⚠️  Falha ao adicionar música: {e}. Vídeo será silencioso.")
    else:
        log.warning(f"⚠️  Música não encontrada em {MUSIC_PATH}. Vídeo será silencioso.")

    # Salva em arquivo temporário e lê como bytes
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        clip.write_videofile(
            tmp_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "main", "-level", "4.0",
                           "-ar", "48000", "-movflags", "+faststart", "-g", "24"],
            verbose=False,
            logger=None,
            temp_audiofile=tmp_path + "_audio.m4a",
        )
        with open(tmp_path, "rb") as f:
            video_bytes = f.read()
        log.info(f"✅ Vídeo gerado: {len(video_bytes)/1024:.0f} KB")
        return video_bytes
    finally:
        # Limpa arquivos temporários
        for p in [tmp_path, tmp_path + "_audio.m4a"]:
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


def _obter_access_token_youtube() -> str:
    """Obtém um Access Token válido usando o Refresh Token do YouTube."""
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id":     YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "refresh_token": YOUTUBE_REFRESH_TOKEN,
            "grant_type":    "refresh_token",
        },
        timeout=15
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise ValueError(f"Sem access_token na resposta: {resp.json()}")
    return token


def publicar_youtube_short(
    video_bytes: bytes,
    titulo: str,
    descricao: str,
    tags: list = None,
) -> str | None:
    """
    Publica um vídeo como YouTube Short (rascunho — requer aprovação manual).

    O YouTube Short é identificado automaticamente quando:
    - O vídeo é vertical (1080x1920)
    - A duração é ≤ 60 segundos
    - O título ou descrição contém #Shorts

    Args:
        video_bytes: Bytes do vídeo MP4.
        titulo:      Título do Short.
        descricao:   Descrição com hashtags.
        tags:        Lista de tags opcionais.

    Retorna:
        str: ID do vídeo publicado, ou None em caso de falha.
    """
    import tempfile

    log.info("📺 Publicando no YouTube Shorts...")

    if not all([YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN]):
        log.warning("⚠️  Credenciais do YouTube não configuradas — pulando.")
        return None

    try:
        access_token = _obter_access_token_youtube()
    except Exception as e:
        log.error(f"❌ Falha ao obter access token YouTube: {e}")
        return None

    # Garante que #Shorts está na descrição (necessário para o algoritmo)
    if "#Shorts" not in descricao and "#shorts" not in descricao:
        descricao = "#Shorts\n\n" + descricao

    # Metadados do vídeo
    metadata = {
        "snippet": {
            "title":       titulo[:100],   # YouTube limita título a 100 chars
            "description": descricao[:5000],
            "tags":        (tags or []) + ["ubatuba", "shorts", "vivendoubatuba"],
            "categoryId":  "22",           # 22 = People & Blogs
        },
        "status": {
            "privacyStatus":           "public",
            "selfDeclaredMadeForKids": False,
        }
    }

    # Salva vídeo em arquivo temporário para upload
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name

    try:
        # Upload resumável — necessário para vídeos
        # Etapa 1: Inicia o upload e obtém a URL de upload
        init_resp = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos"
            "?uploadType=resumable&part=snippet,status",
            headers={
                "Authorization":   f"Bearer {access_token}",
                "Content-Type":    "application/json",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(len(video_bytes)),
            },
            json=metadata,
            timeout=30
        )
        init_resp.raise_for_status()
        upload_url = init_resp.headers.get("Location")

        if not upload_url:
            raise ValueError("URL de upload não retornada pelo YouTube")

        # Etapa 2: Envia o vídeo
        with open(tmp_path, "rb") as f:
            upload_resp = requests.put(
                upload_url,
                headers={
                    "Content-Type":   "video/mp4",
                    "Content-Length": str(len(video_bytes)),
                },
                data=f,
                timeout=120
            )
        upload_resp.raise_for_status()

        video_id = upload_resp.json().get("id")
        log.info(f"🎉 YouTube Short publicado! ID: {video_id}")
        log.info(f"   URL: https://youtube.com/shorts/{video_id}")
        return video_id

    except requests.exceptions.HTTPError as e:
        log.error(f"❌ Erro HTTP YouTube: {e.response.status_code} — {e.response.text[:300]}")
        return None
    except Exception as e:
        log.error(f"❌ Erro ao publicar no YouTube: {e}")
        return None
    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass


# =============================================================================
# FTP — Upload e delete de vídeos para Instagram Stories
# =============================================================================

def fazer_upload_ftp(video_bytes: bytes, nome_arquivo: str) -> str:
    """
    Faz upload de um vídeo MP4 para o servidor FTP e retorna a URL pública.
    O arquivo fica disponível temporariamente para uso nas APIs.

    Args:
        video_bytes:   Bytes do vídeo MP4.
        nome_arquivo:  Nome do arquivo (ex: 'clima_20260602.mp4').

    Retorna:
        str: URL pública do vídeo hospedado.
    """
    log.info(f"📤 Upload FTP: {nome_arquivo}...")
    try:
        ftp = ftplib.FTP()
        ftp.connect(FTP_HOST, 21, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(True)
        ftp.cwd(FTP_PASTA)

        # Upload do arquivo
        ftp.storbinary(f"STOR {nome_arquivo}", io.BytesIO(video_bytes))
        ftp.quit()

        url = f"{FTP_URL.rstrip('/')}/{nome_arquivo}"
        log.info(f"✅ Upload FTP OK: {url}")
        return url

    except Exception as e:
        log.error(f"❌ Erro no upload FTP: {e}")
        raise


def deletar_ftp(nome_arquivo: str) -> bool:
    """
    Deleta um arquivo do servidor FTP após a publicação.

    Args:
        nome_arquivo: Nome do arquivo a deletar.

    Retorna:
        bool: True se deletado com sucesso.
    """
    log.info(f"🗑️  Deletando do FTP: {nome_arquivo}...")
    try:
        ftp = ftplib.FTP()
        ftp.connect(FTP_HOST, 21, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(True)
        ftp.cwd(FTP_PASTA)
        ftp.delete(nome_arquivo)
        ftp.quit()
        log.info(f"✅ Arquivo deletado do FTP: {nome_arquivo}")
        return True
    except Exception as e:
        log.warning(f"⚠️  Falha ao deletar {nome_arquivo} do FTP: {e}")
        return False


def executar_agente():
    """
    Pipeline editorial por dia da semana:

    TODOS OS DIAS:
        ☁️  Story Clima/Tempo

    SEG / TER / QUA / QUI / SÁB / DOM:
        📌 Story + 📸 Feed — Notícia destaque do dia (tema de maior impacto)

    SEXTA-FEIRA:
        📋 Story + 📸 Feed — Resumo da Semana (5-10 notícias dos últimos 7 dias)
    """
    log.info("=" * 60)
    log.info(f"🤖 VIVENDO EM UBATUBA v5.0 — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    log.info("=" * 60)

    HISTORICO = "historico_posts.jsonl"

    for nome, val in {
        "TAVILY_API_KEY": TAVILY_API_KEY, "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "IG_ACCESS_TOKEN": IG_ACCESS_TOKEN, "IG_USER_ID": IG_USER_ID,
        "IMGBB_API_KEY": IMGBB_API_KEY,
    }.items():
        if not val:
            log.error(f"❌ '{nome}' não configurado no .env")
            return False

    if not FTP_PASS:
        log.warning("⚠️  FTP_PASS vazio — Stories em vídeo falharão (erro 530). Adicione FTP_PASS no .env")

    if not FUNDO_URLS:
        log.error("❌ 'FUNDO_URLS' vazio — adicione ao menos uma URL no .env")
        return False

    # Sorteia imagem de fundo — mesma para todos os posts do dia
    fundo_do_dia = random.choice(FUNDO_URLS)
    log.info(f"🖼️  Imagem sorteada ({FUNDO_URLS.index(fundo_do_dia)+1}/{len(FUNDO_URLS)}): {fundo_do_dia}")

    # Detecta dia da semana (0=seg, 4=sex, 5=sab, 6=dom)
    dia_semana = datetime.now().weekday()
    eh_sexta   = dia_semana == 4
    DIAS = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
    log.info(f"📅 Dia: {DIAS[dia_semana]}{' — 📋 RESUMO DA SEMANA' if eh_sexta else ''}")

    ts = datetime.now().strftime("%Y%m%d_%H%M")

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLICAÇÃO 1 — STORY CLIMA (todos os dias)
    # ══════════════════════════════════════════════════════════════════════════
    log.info("\n" + "─"*50)
    log.info("☁️  PUBLICAÇÃO 1: Story Clima/Tempo")
    log.info("─"*50)

    try:
        noticias_clima = buscar_clima_apenas()   # busca focada só em tempo
        clima = gerar_conteudo_clima(noticias_clima)
    except Exception as e:
        log.error(f"❌ Clima: {e}"); clima = "PULAR"

    story_clima_id   = None
    youtube_clima_id = None
    if clima != "PULAR":
        try:
            titulo_c    = clima["titulo"]
            subtitulo_c = clima["subtitulo"]
            corpo_c     = clima["corpo"]
            cta_c       = clima["cta"]
            hashtags_c  = clima["hashtags"]
            condicao_c  = clima.get("condicao", "VARIAVEL")
            temps_c     = clima.get("temperaturas") or ""
            hashtags_c  = _garantir_hashtags(hashtags_c)
            legenda_c   = f"{titulo_c}\n\n{temps_c + chr(10) if temps_c else ''}{corpo_c}\n\n{cta_c}\n\n{hashtags_c}"
            log.info(f"📝 Clima: {titulo_c} [{condicao_c}]")

            fundo_clima = _escolher_fundo_clima(condicao_c)

            # Gera imagem e converte em vídeo (usado em ambas as plataformas)
            bytes_sc_img  = gerar_card(titulo_c, subtitulo_c, fundo_clima, (1080, 1920))
            video_bytes_c = gerar_video_short(bytes_sc_img, duracao=10)

            # Tenta Story como vídeo; fallback automático para imagem se falhar
            try:
                nome_video_c  = f"clima_{ts}.mp4"
                url_video_ftp = fazer_upload_ftp(video_bytes_c, nome_video_c)
                cid = _criar_container_video(url_video_ftp, is_story=True)
                res = _publicar_container(cid, "STORY CLIMA (vídeo)")
                story_clima_id = res.get("id")
                log.info(f"✅ Story Clima (vídeo) publicado! ID: {story_clima_id}")
                deletar_ftp(nome_video_c)
            except Exception as e_video:
                log.warning(f"⚠️  Story vídeo falhou ({e_video}) — publicando como imagem...")
                try:
                    url_img_c = fazer_upload_imgbb(bytes_sc_img, f"ubatuba_clima_story_{ts}")
                    cid = _criar_container(url_img_c, is_story=True)
                    res = _publicar_container(cid, "STORY CLIMA (imagem)")
                    story_clima_id = res.get("id")
                    log.info(f"✅ Story Clima (imagem fallback) publicado! ID: {story_clima_id}")
                except Exception as e_img:
                    log.error(f"❌ Story Clima imagem também falhou: {e_img}")

        except Exception as e:
            log.error(f"❌ Falha Story Clima IG: {e}")
            video_bytes_c = None

        # YouTube Clima — independente do Instagram
        try:
            descricao_yt = f"{legenda_c}\n\n#Shorts #ubatuba #vivendoubatuba #clima"
            # Reutiliza video_bytes_c já gerado acima (evita regerar e corrige
            # o NameError 'bytes_sc is not defined' que existia aqui antes)
            if video_bytes_c is None:
                video_bytes_c = gerar_video_short(bytes_sc_img, duracao=10)
            youtube_clima_id = publicar_youtube_short(
                video_bytes_c,
                titulo=f"UBATUBA - {titulo_c}",
                descricao=descricao_yt,
                tags=["ubatuba", "clima", "tempo", "litoral norte"]
            )
        except Exception as e:
            log.error(f"❌ YouTube Clima: {e}")
            youtube_clima_id = None

    time.sleep(8)

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLICAÇÃO 2A — SEXTA: Resumo da Semana
    # ══════════════════════════════════════════════════════════════════════════
    story_p2_id         = None
    post_p2_id          = None
    tema_log            = None
    youtube_tematico_id = None
    # Nota: youtube_clima_id e video_bytes_c já foram definidos no bloco de
    # Publicação 1 — NÃO resetar aqui para não apagar o resultado do clima.

    if eh_sexta:
        log.info("\n" + "─"*50)
        log.info("📋 PUBLICAÇÃO 2: Resumo da Semana")
        log.info("─"*50)

        try:
            noticias_semana = buscar_noticias_semana()
            resumo = gerar_resumo_semana(noticias_semana)
        except Exception as e:
            log.error(f"❌ Resumo: {e}"); resumo = "PULAR"

        if resumo != "PULAR":
            try:
                itens      = resumo["itens"]
                corpo_r    = resumo["corpo"]
                cta_r      = resumo["cta"]
                hashtags_r = resumo["hashtags"]
                tema_log   = "RESUMO DA SEMANA"

                # Monta legenda com lista numerada
                lista_txt  = "\n".join(
                    f"{i+1}. {it['emoji']} {it['texto']}"
                    for i, it in enumerate(itens)
                )
                hashtags_r = _garantir_hashtags(hashtags_r)
                legenda_r  = f"📋 Resumo da Semana\n\n{corpo_r}\n\n{lista_txt}\n\n{cta_r}\n\n{hashtags_r}"
                log.info(f"📝 Resumo com {len(itens)} itens")

                # Story resumo
                bytes_sr = gerar_card_resumo(itens, fundo_do_dia, (1080, 1920))
                url_sr   = fazer_upload_imgbb(bytes_sr, f"ubatuba_resumo_story_{ts}")
                cid      = _criar_container(url_sr, is_story=True)
                res      = _publicar_container(cid, "STORY RESUMO")
                story_p2_id = res.get("id")

                time.sleep(8)

                # Feed resumo
                bytes_fr = gerar_card_resumo(itens, fundo_do_dia, (1080, 1080))
                url_fr   = fazer_upload_imgbb(bytes_fr, f"ubatuba_resumo_feed_{ts}")
                cid      = _criar_container(url_fr, legenda_r, is_story=False)
                res      = _publicar_container(cid, "FEED RESUMO")
                post_p2_id = res.get("id")

            except Exception as e:
                log.error(f"❌ Falha Resumo da Semana IG: {e}")

            # YouTube Resumo — independente do Instagram
            try:
                descricao_yt = f"{legenda_r}\n\n#Shorts #ubatuba #vivendoubatuba #resumodasemana"
                video_bytes_r = gerar_video_short(bytes_sr, duracao=10)
                youtube_tematico_id = publicar_youtube_short(
                    video_bytes_r,
                    titulo="UBATUBA - Resumo da Semana",
                    descricao=descricao_yt,
                    tags=["ubatuba", "resumo", "semana", "litoral norte"]
                )
            except Exception as e:
                log.error(f"❌ YouTube Resumo: {e}")
                youtube_tematico_id = None

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLICAÇÃO 2B — DEMAIS DIAS: Notícia destaque do dia
    # ══════════════════════════════════════════════════════════════════════════
    else:
        log.info("\n" + "─"*50)
        log.info("📌 PUBLICAÇÃO 2: Notícia destaque do dia")
        log.info("─"*50)

        try:
            noticias = buscar_noticias_ubatuba()
            tematico = gerar_conteudo_tematico(noticias)
        except Exception as e:
            log.error(f"❌ IA Temático: {e}"); tematico = "PULAR"

        if tematico != "PULAR":
            try:
                titulo_t    = tematico["titulo"]
                subtitulo_t = tematico["subtitulo"]
                corpo_t     = tematico["corpo"]
                cta_t       = tematico["cta"]
                hashtags_t  = tematico["hashtags"]
                tema_log    = tematico.get("tema", "?")
                motivo      = tematico.get("motivo_escolha", "")
                hashtags_t  = _garantir_hashtags(hashtags_t)
                legenda_t   = f"{titulo_t}\n\n{corpo_t}\n\n{cta_t}\n\n{hashtags_t}"

                log.info(f"📝 Tema: {tema_log}")
                log.info(f"💡 Motivo: {motivo}")

                nome_tema = tema_log.lower() if tema_log != "?" else "post"
                bytes_st  = gerar_card(titulo_t, subtitulo_t, fundo_do_dia, (1080, 1920))
                bytes_ft  = gerar_card(titulo_t, subtitulo_t, fundo_do_dia, (1080, 1080))
                url_st    = fazer_upload_imgbb(bytes_st, f"ubatuba_{nome_tema}_story_{ts}")
                url_ft    = fazer_upload_imgbb(bytes_ft, f"ubatuba_{nome_tema}_feed_{ts}")

                # Story temático — Instagram
                story_p2_id = None
                try:
                    cid = _criar_container(url_st, is_story=True)
                    res = _publicar_container(cid, f"STORY {tema_log}")
                    story_p2_id = res.get("id")
                except Exception as e:
                    log.error(f"❌ Story IG {tema_log}: {e}")

                time.sleep(8)

                # Feed temático — Instagram
                post_p2_id = None
                try:
                    cid = _criar_container(url_ft, legenda_t, is_story=False)
                    res = _publicar_container(cid, f"FEED {tema_log}")
                    post_p2_id = res.get("id")
                except Exception as e:
                    log.error(f"❌ Feed IG {tema_log}: {e}")

                time.sleep(5)

            except Exception as e:
                log.error(f"❌ Falha post temático: {e}")

            # YouTube — independente do Instagram
            if tematico != "PULAR":
                try:
                    descricao_yt = f"{legenda_t}\n\n#Shorts {hashtags_t}"
                    video_bytes_t = gerar_video_short(bytes_st, duracao=10)
                    youtube_tematico_id = publicar_youtube_short(
                        video_bytes_t,
                        titulo=f"UBATUBA - {titulo_t}",
                        descricao=descricao_yt,
                        tags=["ubatuba", tema_log.lower() if tema_log else "ubatuba"]
                    )
                except Exception as e:
                    log.error(f"❌ YouTube {tema_log}: {e}")
                    youtube_tematico_id = None

    # ── Salva histórico ───────────────────────────────────────────────────────
    with open(HISTORICO, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "data":          datetime.now().isoformat(),
            "dia_semana":    DIAS[dia_semana],
            "tipo_p2":       "RESUMO_SEMANA" if eh_sexta else "DESTAQUE_DIA",
            "tema":          tema_log,
            "story_clima":   story_clima_id,
            "story_p2":      story_p2_id,
            "post_p2":       post_p2_id,
        }, ensure_ascii=False) + "\n")

    # ── Resumo final ──────────────────────────────────────────────────────────
    log.info("\n" + "="*60)
    log.info("📊 RESUMO DA EXECUÇÃO:")
    log.info(f"  ☁️  Story Clima IG:    {'✅' if story_clima_id else '❌'}")
    log.info(f"  📺 YouTube Clima:     {'✅' if youtube_clima_id else '❌'}")
    if eh_sexta:
        log.info(f"  📋 Story Resumo IG:  {'✅' if story_p2_id else '❌'}")
        log.info(f"  📋 Feed Resumo IG:   {'✅' if post_p2_id else '❌'}")
        log.info(f"  📺 YouTube Resumo:   {'✅' if youtube_tematico_id else '❌'}")
    else:
        log.info(f"  📌 Story [{tema_log or '?'}] IG: {'✅' if story_p2_id else '❌'}")
        log.info(f"  📸 Feed  [{tema_log or '?'}] IG: {'✅' if post_p2_id else '❌'}")
        log.info(f"  📺 YouTube [{tema_log or '?'}]:  {'✅' if youtube_tematico_id else '❌'}")
    log.info("="*60)
    return True


if __name__ == "__main__":
    exit(0 if executar_agente() else 1)