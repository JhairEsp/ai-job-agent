"""Portal DEMO: ofertas de muestra para probar todo el flujo end-to-end
sin conectar ninguna cuenta real. Claramente marcado como DEMO.
"""
from __future__ import annotations

from app.models.job import JobPosting
from app.models.profile import SearchPreferences
from app.portals.base_portal import BasePortal

DEMO_JOBS = [
    JobPosting(
        title="Practicante de Inteligencia de Negocios",
        company="Claro Perú (DEMO)",
        location="Lima",
        salary="S/ 1,200",
        modality="Híbrido",
        url="https://demo.aijoajob.local/ofertas/claro-practicante-bi",
        portal="demo",
        description=(
            "Buscamos practicante de BI, estudiante de Ingeniería de Sistemas "
            "o afines. Requisitos: SQL, Excel avanzado. Deseable: Power BI y "
            "Data Warehouse. Apoyarás en reportes y dashboards del área comercial."
        ),
    ),
    JobPosting(
        title="Practicante de Sistemas",
        company="TechAndina (DEMO)",
        location="Lima",
        salary="S/ 1,000",
        modality="Presencial",
        url="https://demo.aijoajob.local/ofertas/techandina-practicante",
        portal="demo",
        description=(
            "Practicante de sistemas para soporte TI y desarrollo interno. "
            "Se valora conocimiento en Python, redes y atención al usuario."
        ),
    ),
    JobPosting(
        title="Analista de Sistemas Junior",
        company="Grupo Andino (DEMO)",
        location="Remoto",
        salary="S/ 2,000",
        modality="Remoto",
        url="https://demo.aijoajob.local/ofertas/grupo-andino-analista",
        portal="demo",
        description=(
            "Analista junior con base en SQL Server y Postgres. Se requiere "
            "egresado o bachiller en Ingeniería de Sistemas. Modalidad remota."
        ),
    ),
    JobPosting(
        title="Soporte TI - Medio Tiempo",
        company="Municipalidad Demo (DEMO)",
        location="Callao",
        salary="S/ 800",
        modality="Presencial",
        url="https://demo.aijoajob.local/ofertas/muni-soporte",
        portal="demo",
        description=(
            "Soporte técnico de medio tiempo: mantenimiento de equipos, "
            "help desk nivel 1 y cableado estructurado básico."
        ),
    ),
    JobPosting(
        title="Desarrollador Backend Senior (5+ años)",
        company="Fintech Demo (DEMO)",
        location="Lima",
        salary="S/ 12,000",
        modality="Híbrido",
        url="https://demo.aijoajob.local/ofertas/fintech-senior",
        portal="demo",
        description=(
            "Buscamos desarrollador senior con 5+ años de experiencia en Java, "
            "microservicios y AWS. Liderazgo técnico de equipos."
        ),
    ),
    JobPosting(
        title="Practicante BI - Power BI",
        company="Retail Demo (DEMO)",
        location="Lima",
        salary="S/ 1,000",
        modality="Híbrido",
        url="https://demo.aijoajob.local/ofertas/retail-practicante-bi",
        portal="demo",
        description=(
            "Practicante de Business Intelligence con manejo de Power BI, "
            "Excel y nociones de ETL. Estudiantes de últimos ciclos."
        ),
    ),
]


class DemoPortal(BasePortal):
    name = "demo"
    display_name = "🧪 Demo (ofertas de prueba)"
    home_url = "https://demo.aijoajob.local"
    requires_login = False
    supports_apply = True

    def build_search_url(self, query: str, location: str) -> str:
        return self.home_url

    def parse_search_results(self, html: str) -> list[JobPosting]:
        return []

    def parse_description(self, html: str) -> str:
        return ""

    async def search(self, browser, preferences: SearchPreferences) -> list[JobPosting]:
        """Filtra las ofertas demo por los puestos/ubicaciones del usuario."""
        wanted = [p.lower() for p in preferences.positions]
        results = []
        for job in DEMO_JOBS:
            if wanted and not any(
                token in job.title.lower()
                for p in wanted
                for token in p.split()
            ):
                continue
            results.append(JobPosting(**job.to_dict()))
        return results

    async def apply(self, browser, job, applicant, answers) -> str:
        """Postulación simulada: el portal demo acepta siempre."""
        return "submitted"
