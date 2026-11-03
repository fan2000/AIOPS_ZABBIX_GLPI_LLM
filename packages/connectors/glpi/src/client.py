"""Client asynchrone pour l'API REST de GLPI (v9.5 et v10.0)."""

import os
from typing import Any, Dict, List, Optional
import httpx
from packages.contracts.src.glpi import (
    GlpiAssetRead,
    GlpiFollowupCreate,
    GlpiKnowledgeItemRead,
    GlpiSolutionCreate,
    GlpiTicketCreate,
)


class GlpiClient:
    """Client REST asynchrone pour GLPI avec gestion de session et entités."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        app_token: Optional[str] = None,
        user_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        default_entity_id: int = 0,
    ):
        self.api_url = (api_url or os.getenv("GLPI_API_URL", "http://localhost:8088/apirest.php")).rstrip("/")
        self.app_token = app_token or os.getenv("GLPI_APP_TOKEN")
        self.user_token = user_token or os.getenv("GLPI_USER_TOKEN")
        self.username = username or os.getenv("GLPI_USERNAME", "glpi")
        self.password = password or os.getenv("GLPI_PASSWORD", "glpi")
        self.default_entity_id = int(os.getenv("GLPI_DEFAULT_ENTITY_ID", str(default_entity_id)))
        self._session_token: Optional[str] = None

    def _get_headers(self, with_session: bool = True) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.app_token:
            headers["App-Token"] = self.app_token
        if with_session and self._session_token:
            headers["Session-Token"] = self._session_token
        return headers

    async def init_session(self) -> str:
        """Initialise la session GLPI via User-Token ou Basic Auth."""
        headers = self._get_headers(with_session=False)
        auth = None
        if self.user_token:
            headers["Authorization"] = f"user_token {self.user_token}"
        else:
            auth = (self.username, self.password)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.api_url}/initSession", headers=headers, auth=auth)
            resp.raise_for_status()
            data = resp.json()
            self._session_token = data.get("session_token")
            if not self._session_token:
                raise RuntimeError("GLPI initSession n'a pas retourné de session_token")
            return self._session_token

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Exécute une requête avec tentative de ré-authentification si 401."""
        if not self._session_token:
            await self.init_session()

        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                params=params,
                json=json_data,
            )
            if resp.status_code == 401:
                # Session expirée, tentative de réinitialisation
                await self.init_session()
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(),
                    params=params,
                    json=json_data,
                )
            resp.raise_for_status()
            return resp.json() if resp.text else {}

    async def search_computer(self, host_name: str) -> Optional[GlpiAssetRead]:
        """Recherche un équipement par son nom dans la CMDB GLPI."""
        params = {
            "criteria[0][field]": "1",  # Nom d'hôte
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": host_name,
            "forcedisplay[0]": "2",    # ID
            "forcedisplay[1]": "1",    # Nom
        }
        res = await self._request("GET", "search/Computer", params=params)
        data = res.get("data", [])
        if not data:
            return None
        row = data[0]
        return GlpiAssetRead(
            id=int(row.get("2", 1)),
            name=str(row.get("1", host_name)),
            item_type="Computer",
            serial=row.get("5"),
            entity_id=int(row.get("80", self.default_entity_id)),
        )

    async def create_ticket(self, ticket: GlpiTicketCreate) -> int:
        """Crée un ticket d'incident dans GLPI."""
        payload: Dict[str, Any] = {
            "input": {
                "name": ticket.name,
                "content": ticket.content,
                "status": ticket.status.value,
                "urgency": ticket.urgency.value,
                "impact": ticket.impact.value,
                "entities_id": ticket.entities_id,
            }
        }
        if ticket.items_id:
            payload["input"]["_items_id"] = ticket.items_id

        res = await self._request("POST", "Ticket", json_data=payload)
        return int(res.get("id"))

    async def add_private_followup(self, followup: GlpiFollowupCreate) -> int:
        """Ajoute un suivi privé dans le ticket pour consigner l'analyse IA ou l'exécution."""
        payload = {
            "input": {
                "itemtype": followup.itemtype,
                "items_id": followup.items_id,
                "content": followup.content,
                "is_private": followup.is_private,
            }
        }
        res = await self._request("POST", f"Ticket/{followup.items_id}/ITILFollowup", json_data=payload)
        return int(res.get("id", 0))

    async def propose_solution(self, solution: GlpiSolutionCreate) -> int:
        """Ajoute une proposition formelle de solution soumise au technicien."""
        payload = {
            "input": {
                "itemtype": solution.itemtype,
                "items_id": solution.items_id,
                "content": solution.content,
                "solutiontypes_id": solution.solutiontypes_id,
            }
        }
        res = await self._request("POST", f"Ticket/{solution.items_id}/ITILSolution", json_data=payload)
        return int(res.get("id", 0))

    async def get_knowledge_items(self, limit: int = 50) -> List[GlpiKnowledgeItemRead]:
        """Récupère les articles de la base de connaissances GLPI pour vectorisation."""
        params = {"range": f"0-{limit}"}
        items = await self._request("GET", "KnowbaseItem", params=params)
        results = []
        for it in items:
            results.append(
                GlpiKnowledgeItemRead(
                    id=int(it["id"]),
                    name=it.get("name", "Sans titre"),
                    answer=it.get("answer", ""),
                    entities_id=int(it.get("entities_id", 0)),
                    is_faq=bool(it.get("is_faq", False)),
                )
            )
        return results


glpi_client = GlpiClient()
