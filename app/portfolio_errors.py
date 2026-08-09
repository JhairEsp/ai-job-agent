"""Mensajes de error de portales, presentables al usuario."""

PORTAL_ERROR_MESSAGES = {
    "captcha": (
        "pide CAPTCHA/verificación humana. Entra al portal con el botón "
        "🔐 Conectar y resuélvelo manualmente; nunca intentamos evitarlos."
    ),
    "browser": (
        "el navegador no está disponible en este equipo "
        "(instala Chromium con `playwright install chromium`)."
    ),
    "TimeoutError": "la página tardó demasiado en responder.",
    "NetworkError": "problema de red al contactar el portal.",
}
