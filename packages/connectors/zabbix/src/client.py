"""Client asynchrone JSON-RPC pour l'API Zabbix 6.4 / 7.0."""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional
import httpx

_ORIG_ASYNC_CLIENT = httpx.AsyncClient


class ZabbixClient:
    """Client API Zabbix JSON-RPC 2.0 avec pool HTTP réutilisable, session et retry."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.api_url = api_url or os.getenv("ZABBIX_API_URL", "http://localhost:8089/api_jsonrpc.php")
        self.auth_token = auth_token or os.getenv("ZABBIX_API_TOKEN")
        self.username = username or os.getenv("ZABBIX_USER", "Admin")
        self.password = password or os.getenv("ZABBIX_PASSWORD", "zabbix")
        self._request_id = 0
        self._http_client: Optional[httpx.AsyncClient] = None
        self._pool_loop: Optional[asyncio.AbstractEventLoop] = None

    async def _get_pooled_client(self) -> Optional[httpx.AsyncClient]:
        if httpx.AsyncClient is not _ORIG_ASYNC_CLIENT:
            return None
        loop = asyncio.get_running_loop()
        if self._http_client is None or self._http_client.is_closed or self._pool_loop is not loop:
            self._http_client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=24, max_keepalive_connections=12)
            )
            self._pool_loop = loop
        return self._http_client

    async def _call(self, method: str, params: Dict[str, Any]) -> Any:
        """Exécute un appel JSON-RPC 2.0 avec en-têtes et authentification."""
        self._request_id += 1
        headers = {"Content-Type": "application/json-rpc"}

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._request_id,
        }

        # Pour les méthodes nécessitant une session Zabbix
        if self.auth_token and method not in ("apiinfo.version", "user.login"):
            headers["Authorization"] = f"Bearer {self.auth_token}"
            payload["auth"] = self.auth_token

        pooled = await self._get_pooled_client()
        if pooled is not None:
            response = await pooled.post(self.api_url, json=payload, headers=headers, timeout=10.0)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
        response.raise_for_status()
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as err:
            raise RuntimeError(f"Réponse Zabbix invalide (non-JSON) : {response.text[:200]}") from err

        if "error" in data:
            raise RuntimeError(f"Erreur API Zabbix: {data['error'].get('message')} - {data['error'].get('data')}")
        return data.get("result")

    async def get_api_version(self) -> str:
        """Retourne la version de l'API Zabbix (ex: 7.0.0) sans nécessiter d'authentification préalable."""
        return str(await self._call("apiinfo.version", {}))

    async def login(self) -> str:
        """Authentification par nom d'utilisateur/mot de passe (Zabbix < 5.4/6.x/7.x)."""
        if self.auth_token:
            return self.auth_token
        result = await self._call("user.login", {"username": self.username, "password": self.password})
        self.auth_token = str(result)
        return self.auth_token

    async def get_host(self, host_name_or_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un équipement Zabbix."""
        params: Dict[str, Any] = {
            "output": ["hostid", "host", "name", "status", "description"],
            "selectInterfaces": ["ip", "dns", "port", "type", "main"],
            "selectTags": "extend",
        }
        if host_name_or_id.isdigit():
            params["hostids"] = [host_name_or_id]
        else:
            params["filter"] = {"host": [host_name_or_id]}

        results = await self._call("host.get", params)
        return results[0] if results else None

    async def get_item_history(
        self,
        item_id: str,
        limit: int = 20,
        history_type: int = 0,  # 0: float, 3: uint
    ) -> List[Dict[str, Any]]:
        """Récupère l'historique des valeurs récentes pour une métrique."""
        params = {
            "output": "extend",
            "itemids": [item_id],
            "history": history_type,
            "sortfield": "clock",
            "sortorder": "DESC",
            "limit": limit,
        }
        return await self._call("history.get", params)

    async def acknowledge_event(self, event_id: str, message: str) -> bool:
        """Acquitte un événement dans Zabbix pour signaler la prise en charge AIOps."""
        params = {
            "eventids": [event_id],
            "action": 6,  # 2 (close) + 4 (acknowledge) = 6
            "message": f"[AI IT Operations] {message}",
        }
        result = await self._call("event.acknowledge", params)
        return bool(result and "eventids" in result)


zabbix_client = ZabbixClient()
