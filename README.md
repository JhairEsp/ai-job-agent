# 🤖 AI Job Agent

Asistente personal de búsqueda y postulación laboral, controlado desde **Telegram**
y potenciado por **Groq** como motor de IA.

> **Producto completo** — búsqueda multi-portal, análisis con IA (score 0-100),
> postulación guiada con confirmaciones, tracker y auto-búsqueda programada.

---

## ✨ Funcionalidades

- 🤖 **Bot de Telegram** con menú principal interactivo (botones inline) y
  notificación de arranque ("escribe /start").
- 💬 **Chat natural con Groq**: conversa sin comandos; el asistente conoce tu
  perfil y tu CV (sin inventar datos).
- 👤 **Onboarding progresivo**: datos personales + preferencias laborales
  (ubicaciones múltiples, puestos objetivo, salario mínimo, modalidad, jornada).
- 📄 **CV en Markdown** (`data/profile/cv.md`): lectura a estructura interna,
  resumen en Telegram y **subida de `.md` con respaldo automático**.
- 🌐 **Portales laborales**: LinkedIn, Computrabajo, Indeed, Bumeran + portal
  🧪 DEMO para probar todo sin cuentas reales. Activación por botones.
- 🔐 **Conexión segura de cuentas**: sesiones persistentes de Playwright por
  portal; jamás se piden ni guardan contraseñas.
- 🔎 **Búsqueda multi-portal** con deduplicación, ranking heurístico y
  **análisis IA (Groq)** de las mejores ofertas con score 0-100.
- 🔥 **TOP MATCHES** con tarjetas por oferta: 🔗 Ver oferta · 🤖 Analizar ·
  🚀 Postular · ⭐ Guardar · ❌ Ignorar.
- 🚀 **Postulación guiada** con 3 confirmaciones: confirmación → respuesta
  generada (usar/editar/regenerar) → ⚠️ **REVISIÓN FINAL** → ENVIAR.
  Pre-llenado de formularios con Playwright cuando el portal lo permite.
- 📋 **Tracker de postulaciones** con estados (POSTULADO, Entrevista, Oferta…)
  actualizables desde Telegram.
- 🤖 **AUTO SEARCH**: búsquedas automáticas cada 6/12/24 h y notificación solo
  de ofertas nuevas con match ≥ umbral configurable.

## 🚀 Instalación

```bash
cd ai-job-agent
python -m venv .venv && source .venv/bin/activate   # Python 3.12+
pip install -r requirements.txt
playwright install chromium        # necesario para portales reales
cp .env.example .env               # completa TELEGRAM_BOT_TOKEN y GROQ_API_KEY
python main.py
```

Luego abre tu bot en Telegram y envía `/start`.

## 🧪 Probar sin cuentas reales

El portal **🧪 Demo** viene activado por defecto. Después del onboarding:

1. 🔎 **Buscar trabajos** → verás ofertas de ejemplo con su match.
2. 🤖 **Analizar** → análisis IA con fortalezas, brechas y recomendación.
3. 🚀 **Postular** → flujo completo de confirmaciones y registro en el tracker.

Cuando quieras ofertas reales, activa los portales en 🌐 **Portales** y conecta
tu sesión una vez desde el navegador.

> ⚠️ Los selectores HTML de los portales cambian con el tiempo. Si un portal
> deja de devolver ofertas, revisa sus selectores en `app/portals/<portal>.py`.
> Ante un CAPTCHA, el bot se detiene y te pide resolverlo manualmente (regla
> inviolable: nunca se intentan evadir).

## 📁 Estructura

```
ai-job-agent/
├── app/
│   ├── ai/            # Groq: cliente, analizador (score), generador de respuestas, asistente
│   ├── bot/           # Telegram: handlers (onboarding, búsqueda, apply, tracker…), teclados, vistas
│   ├── portals/       # base_portal + linkedin/computrabajo/indeed/bumeran/demo + registry
│   ├── browser/       # Sesiones persistentes Playwright (1 perfil por portal)
│   ├── applications/  # (reglas de postulación documentadas)
│   ├── cv/            # cv.md → estructura + reemplazo con respaldo
│   ├── database/      # SQLite: users, profile, search_preferences, portals, jobs, applications
│   ├── models/        # Perfil, preferencias, job, análisis, estados
│   ├── services/      # Búsqueda, ranking heurístico, auto-search (JobQueue)
│   ├── utils/         # Logging sin secretos
│   └── portfolio_errors.py
├── data/
│   ├── profile/cv.md        # Tu CV (fuente única de verdad)
│   ├── browser_profiles/    # Sesiones por portal (ignorado por git)
│   ├── jobs/ · applications/
├── prompts/           # analyze_job · match_job · generate_answer (anti-alucinación)
├── tests/             # 44 pruebas (incluye fixtures HTML de portales)
├── .env · .env.example · .gitignore · requirements.txt · main.py
└── README.md
```

## 🔒 Seguridad

- Secretos solo en `.env` (ignorado por git); API keys enmascaradas en UI y logs.
- **Cero contraseñas**: ni en Telegram, ni en SQLite, ni hacia Groq.
- Postulación únicamente tras confirmación explícita (REVISIÓN FINAL → ENVIAR).
- La IA solo usa datos reales de `cv.md`: **prohibido inventar** experiencia,
  estudios, certificaciones o habilidades.
- Ante CAPTCHA/verificación humana: detenerse y avisar. Nunca evadirlos.
- Respeto de las condiciones de uso de cada portal.

## 🧪 Pruebas

```bash
pytest -q    # 44 tests: parseo, DB, ranking, búsqueda integrada, tracker…
```

## 📜 Reglas del agente

Calidad sobre cantidad · No postular sin autorización · No mentir en
postulaciones · No inventar experiencia/certificaciones/habilidades ·
No guardar contraseñas · No enviar credenciales a la IA · No evadir
CAPTCHA · Respetar las condiciones de uso de cada portal.
