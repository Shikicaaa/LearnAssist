# RAG Platforma za Učenje

Platforma za učenje iz sopstvenog materijala sa citatima iz izvora. Studenti učitavaju PDF/DOCX/TXT/MD materijale, postavljaju pitanja i dobijaju odgovore isključivo iz tog materijala sa preciznim citatima.

## Karakteristike

- 📚 **Podrška za više formata**: PDF, DOCX, TXT, MD, tekstualni unos
- 🔍 **RAG sa citatima**: Odgovori su uvek iz materijala sa linkom do izvora i broja strane
- ⚡ **Brzi embedding**: Lokalni embeddings (multilingual-e5-small ili bge-m3) na CPU-u
- 🧠 **LLM fleksibilnost**: Claude, Gemini, Ollama ili OpenAI-kompatibilan server
- 💾 **Keš**: Semantički keš sa lenjavom revalidacijom
- 📊 **Kvizovi**: Automatska generisanja kvizova iz materijala
- 🔐 **Bezbednost**: JWT autentifikacija, Argon2 heš, izolacija korisnika
- 🐳 **Docker**: Kompletan docker-compose za development

## Tech Stack

| Komponenta | Izbor |
|---|---|
| API | FastAPI |
| Baza | PostgreSQL 17 + pgvector |
| LLM | Gemini Flash (default) / Claude / Ollama |
| Embeddings | multilingual-e5-small (default) / bge-m3 |
| Queue | Celery + Redis |
| ORM | SQLAlchemy 2.x + Alembic |
| Auth | JWT + Argon2 |
| Python | 3.10+ |

## Quick Start

### 1. Kloniraj i setup-uj okruženje

```bash
cd /home/shikicaaa/Desktop/RAG_Ucenje

# Virtual environment
python3 -m venv venv
source venv/bin/activate

# Instaliraj zavisnosti
pip install -e .
```

### 2. Konfiguracija

Kopiraj `.env.example` u `.env` i dodaj svoj Gemini API ključ:

```bash
cp .env.example .env
# Uredi .env i dodaj: GEMINI_API_KEY=your_key_here
```

### 3. Pokreni servise sa Docker Compose

```bash
docker compose up -d
```

To pokreće:
- PostgreSQL 17 sa pgvector (port 5432)
- Redis (port 6379)
- FastAPI API (port 8000)
- Celery worker (za background taskove)

### 4. Migracije

```bash
alembic upgrade head
```

### 5. Testiranje

```bash
# Health check
curl http://localhost:8000/health

# Readiness check
curl http://localhost:8000/ready

# API dokumentacija (Swagger)
open http://localhost:8000/docs
```

## Struktura Projekta

```
.
├── app/
│   ├── main.py              # FastAPI aplikacija
│   ├── worker.py            # Celery worker
│   ├── shared/              # Deljeni moduli
│   │   ├── config.py        # Konfiguracija
│   │   ├── database.py      # SQLAlchemy
│   │   ├── exceptions.py    # Greške
│   │   └── logger.py        # Logovanje
│   └── modules/             # Funkcijski moduli
│       ├── auth/            # Autentifikacija (faza 1)
│       ├── sessions/        # Sesije učenja (faza 1)
│       ├── sources/         # Upload materijala (faza 2)
│       ├── embeddings/      # Embedding modeli (faza 2)
│       ├── retrieval/       # Vektorska pretraga (faza 3)
│       ├── chat/            # Chat sa citatima (faza 3)
│       ├── cache/           # Keš (faza 4)
│       ├── artifacts/       # Kvizovi (faza 6)
│       ├── llm/             # LLM provajderi (faza 5)
│       └── jobs/            # Celery taskovi
├── alembic/                 # Migracije baze
├── scripts/                 # Pomoćni skriptovi
├── pyproject.toml           # Zavisnosti
├── docker-compose.yml       # Docker setup
└── README.md                # Ovaj fajl
```

## Redosled Implementacije (7 faza)

**Faza 0 (✅ Temelji)**: Repo, docker-compose, shared/, alembic, health rute
- Status: **GOTOVO** - Svi fondamenti su tu

**Faza 1 (→ Sledeća)**: Auth + sesije
- Register/login/refresh/logout
- Sesije kao "workspace"
- JWT + refresh tokeni + Argon2

**Faza 2**: Ingestion (fajlovi → vektori)
- Parsiranje: PDF, DOCX, TXT, MD
- Chunkovanje sa prelapanjem
- Embedovanje u batch-evima
- TaskQueue + Celery worker

**Faza 3**: Retrieval + chat sa citatima
- Vektorska pretraga
- LLM prompt sa kontekstom
- Odgovori sa citatima (file + page)
- "Ne znam" za van-scope pitanja

**Faza 4**: Keš
- Tačan hash + sličnost
- Lenja revalidacija
- Invalidacija pri brisanju

**Faza 5**: Svi LLM provajderi
- Claude API
- Ollama (lokalno)
- OpenAI-kompatibilan

**Faza 6**: Kvizovi
- Generisanje iz materijala
- Keš po params_hash

**Faza 7**: Evaluacija
- recall@k, MRR, faithfulness
- Kalibracija praga keša

## Lokalni Razvoj

### Restartuj sve servise

```bash
docker compose down
docker compose up -d
```

### Pogledaj logove

```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f postgres
```

### Obradi bazu

```bash
# Prikazi status
alembic current

# Nova migracija (auto)
alembic revision --autogenerate -m "Dodaj novu tabelu"

# Primeni
alembic upgrade head

# Nazad
alembic downgrade -1
```

### Testiranje

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html
```

## Konfiguracija

Sve je u `.env` fajlu. Ključne varijable:

- `LLM_PROVIDER`: `gemini` (default), `ollama`, `openai`
- `GEMINI_API_KEY`: Tvoj Gemini API ključ
- `EMBEDDING_MODEL`: `multilingual-e5-small` ili `bge-m3`
- `CHUNK_SIZE`: Veličina chunkova u tokena (default 500)
- `RETRIEVAL_TOP_K`: Koliko relevantnih chunkova za odgovor (default 5)
- `CACHE_SIMILARITY_THRESHOLD`: Prag za keš pogodak (default 0.93)

## API Endpointi (Faza 0: samo health)

```
GET  /health                      # Liveness
GET  /ready                       # Readiness
GET  /docs                        # Swagger dokumentacija
```

Ostali endpointi dolaze u sledećim fazama:

```
# Auth (Faza 1)
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout

# Sesije (Faza 1)
POST /api/v1/sessions
GET  /api/v1/sessions
GET  /api/v1/sessions/{id}

# Izvori (Faza 2)
POST /api/v1/sessions/{sid}/sources/files
POST /api/v1/sessions/{sid}/sources/text
GET  /api/v1/sessions/{sid}/sources

# Chat (Faza 3)
POST /api/v1/sessions/{sid}/messages
GET  /api/v1/sessions/{sid}/messages

# Kvizovi (Faza 6)
POST /api/v1/sessions/{sid}/quizzes
GET  /api/v1/artifacts
```

## Kontakt

Autor: Shikicaaa  
Email: stefanovicandrijasd@gmail.com
