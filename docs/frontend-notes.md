# Beleške za frontend i deploy

Stvari koje smo odlučili ili otkrili tokom razvoja backend-a, a koje ne smemo da zaboravimo kad
počnemo frontend i postavljanje iza nginx-a. Ništa od ovoga nije implementirano; ovo je spisak
obaveza.

## 1. Autentifikacija preko cookie-ja (odluka)

**Odluka:** frontend koristi cookie autentifikaciju, jer već imamo refresh tokene.

**Zašto:** browserski `EventSource` (koji koristimo za SSE statuse izvora) ne može da pošalje
`Authorization` zaglavlje. Sa cookie-jem se token šalje sam, pa `new EventSource(url,
{ withCredentials: true })` radi bez dodatnih biblioteka.

**Šta treba promeniti u backend-u:**
- `POST /auth/login` i `POST /auth/refresh` postavljaju cookie-je (`Set-Cookie`):
  - refresh token: `HttpOnly`, `Secure`, `SameSite=Strict` (ili `Lax`), `Path=/api/v1/auth`;
  - access token: `HttpOnly`, `Secure`, `SameSite=Lax`, kratak život (15 min).
- `get_current_user` čita token iz cookie-ja, a **ostaje i podrška za `Authorization: Bearer`**,
  da Swagger i `curl` nastave da rade.
- `POST /auth/logout` briše cookie-je (`Max-Age=0`) i opoziva refresh token.
- **CSRF zaštita** (obavezna kad se pređe na cookie-je, jer browser ih šalje automatski):
  `SameSite` + provera zaglavlja `Origin` na rutama koje menjaju stanje (POST, PATCH, DELETE),
  eventualno i CSRF token u zaglavlju.
- **CORS:** `ALLOWED_ORIGINS` već postoji u `.env`, ali CORS middleware još nije dodat. Sa
  cookie-jima mora `allow_credentials=True`, a tada **ne sme** `*` kao dozvoljeni origin.
- Handoff, odeljak 8, već predviđa httpOnly cookie za refresh token ("kad stigne frontend").

## 2. Server-sent events (SSE)

- Ruta: `GET /api/v1/sessions/{sid}/sources/events`. Šalje `snapshot` (svi izvori), pa `source`
  događaj na svaku promenu, i `: keepalive` komentar na svakih 15 s.
- **Token se proverava samo pri povezivanju.** Veza može da traje duže od isteka access tokena.
  Odlučiti da li da server prekida tokove posle određenog vremena (pa klijent ponovo da se poveže
  sa svežim tokenom).
- Brisanje sesije ne zatvara otvorene tokove (ostaju do prekida veze).
- Ako koristimo `fetch` umesto `EventSource` (npr. `@microsoft/fetch-event-source`), može i
  Bearer token. Cookie je ipak jednostavniji.

## 3. Nginx (reverse proxy)

```nginx
# Upload fajlova: limit u aplikaciji je 25 MB po fajlu, a zahtev može imati više fajlova.
# Mora biti >= najvećeg dozvoljenog zahteva, inače nginx vraća 413 pre nego što stigne do nas.
client_max_body_size 30m;

location /api/ {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# SSE rute (statusi izvora i četovanje sa ?stream=true): bez baferovanja i sa dugim čitanjem.
location ~ ^/api/v1/sessions/[^/]+/(sources/events|messages)$ {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;        # inače nginx drži događaje dok se bafer ne napuni
    proxy_cache off;
    gzip off;                   # kompresija takođe baferuje
    proxy_read_timeout 1h;      # podrazumevano je 60 s, a veza može dugo da miruje
}
```

- Aplikacija već šalje `X-Accel-Buffering: no`, ali ovo ne treba da zavisi samo od toga.
- **IP adresa klijenta:** rate limit na login/register i na četu koristi `request.client.host`.
  Iza nginx-a bi to bio IP nginx-a, pa bi svi korisnici delili isti brojač. Treba pokrenuti
  uvicorn sa `--proxy-headers --forwarded-allow-ips=<IP nginx-a>` (ne `*`), da čita
  `X-Forwarded-For`.
- HTTPS završava nginx; zato su cookie-ji `Secure`, a `X-Forwarded-Proto` mora da se prosledi.

## 4. Ostalo što frontend treba da zna

- **Brojevi strana u DOCX-u** postoje samo ako je fajl sačuvan u Wordu. Inače je strana `null`,
  pa citat prikazuje samo naziv izvora.
- **Skenirani PDF-ovi** (bez teksta) završavaju kao `failed` sa porukom; OCR još ne postoji.
- Poruke grešaka API-ja su na engleskom, u obliku `{"error": {"code", "message"}}`; frontend po
  `code` bira tekst koji prikazuje korisniku.
- Probna ruta `POST /api/v1/llm/test` postoji samo kad je `ENVIRONMENT=development`.

## 5. Čet (`POST /api/v1/sessions/{sid}/messages`)

- **Dva režima:** običan (JSON sa odgovorom) i `?stream=true` (SSE). Stream šalje `delta`
  (delovi teksta), pa `citations`, pa `done` (sačuvana poruka sa ID-jem). Ako model pukne usred
  odgovora, stiže `error` događaj, a poruka se **ne** čuva.
- **Greške pre prvog bajta** (limit, nepostojeća sesija, model odbija zahtev) stižu kao obični
  HTTP status (404, 429, 502, 503), a ne kao događaj. Frontend mora da obradi oba slučaja.
- **Citati:** tekst odgovora sadrži oznake `[1]`, `[2]`... Broj odgovara polju `rank` u listi
  `citations`. Klik na oznaku treba da otvori `GET /api/v1/chunks/{chunk_id}` (tekst iza citata).
  Ako je izvor u međuvremenu obrisan, `chunk_id` je `null`, ali `source_title` i strana ostaju.
- **Format odgovora:** model piše Markdown i ume da napiše formule u LaTeX-u (`$f(x) = x^2$`),
  pa frontend treba da renderuje Markdown i, po mogućstvu, KaTeX.
- **Posebni odgovori bez poziva modela:** sesija bez izvora i pitanje bez ikakvog relevantnog
  materijala vraćaju gotovu poruku (`llm_provider` je tada `null`). Pitanje van gradiva model
  odbija sa porukom "Ne mogu da odgovorim...", bez citata.
- **Istorija** (`GET .../messages`) vraća najnoviju poruku prvu; frontend je obrće za prikaz.
- **Prekid veze usred streama:** nepotpun odgovor se ne čuva u istoriji.
- **Prvo pitanje posle pokretanja servera** je sporije dok se učitava model za embedding-e
  (server ga zagreva u pozadini pri startu, oko 10 do 20 s).
