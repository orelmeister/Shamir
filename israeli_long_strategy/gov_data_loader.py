import requests
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class GovDataLoader:
    """
    Client for the Israeli Government Data Portal (data.gov.il) CKAN API.
    Mimics the logic of the 'datagov-mcp' server to fetch real-time macro data.
    """
    BASE_URL = "https://data.gov.il/api/3/action"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "IsraeliShortStrategy/1.0 (AI Autonomous Agent)"
        })

    def fetch_macro_indicators(self) -> Dict:
        """
        Orchestrates the fetching of key real estate indicators.
        """
        logger.info("🏛️ Fetching Macro Data from data.gov.il...")
        
        indicators = {
            "construction_starts": self._get_latest_construction_starts(),
            "new_dwellings_sold": self._get_new_dwellings_sold(),
            "cpi_construction": self._get_construction_input_index()
        }
        
        return indicators

    def _search_package(self, query: str) -> Optional[Dict]:
        """
        Search for a dataset package by name/query.
        """
        try:
            url = f"{self.BASE_URL}/package_search"
            params = {"q": query, "rows": 1}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data["success"] and data["result"]["results"]:
                return data["result"]["results"][0]
            return None
        except Exception as e:
            logger.error(f"Failed to search package '{query}': {e}")
            return None

    def _get_resource_id(self, package: Dict, format_filter: str = "CSV") -> Optional[str]:
        """
        Extract the Resource ID for a specific format (CSV/API).
        """
        for resource in package.get("resources", []):
            if resource.get("format", "").upper() == format_filter:
                return resource["id"]
        # Fallback: take the first one
        if package.get("resources"):
            return package["resources"][0]["id"]
        return None

    def _query_datastore(self, resource_id: str, limit: int = 5, sort: str = "_id desc") -> List[Dict]:
        """
        Query the datastore for a specific resource.
        """
        try:
            url = f"{self.BASE_URL}/datastore_search"
            params = {
                "resource_id": resource_id,
                "limit": limit,
                "sort": sort
            }
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data["success"]:
                return data["result"]["records"]
            return []
        except Exception as e:
            logger.error(f"Failed to query datastore {resource_id}: {e}")
            return []

    # --- Specific Data Fetchers ---

    def _get_latest_construction_starts(self) -> Dict:
        """
        Fetch 'Construction Starts' (התחלות בנייה).
        """
        # Search for the dataset
        pkg = self._search_package("התחלות בנייה")
        if not pkg:
            return {"status": "Not Found", "trend": "Unknown"}
            
        res_id = self._get_resource_id(pkg)
        if not res_id:
            return {"status": "No Resource", "trend": "Unknown"}
            
        # Fetch latest records
        records = self._query_datastore(res_id, limit=5)
        
        # Simple trend analysis (mock logic as data structure varies)
        # In a real scenario, we'd parse the specific columns (Year, Quarter, Total)
        return {
            "source": pkg["title"],
            "latest_data": records,
            "trend": "Analyzing..." # Placeholder for AI to interpret
        }

    def _get_new_dwellings_sold(self) -> Dict:
        """
        Fetch 'New Dwellings Sold' (דירות חדשות שנמכרו).
        """
        pkg = self._search_package("דירות חדשות שנמכרו")
        if not pkg:
            return {"status": "Not Found"}
            
        res_id = self._get_resource_id(pkg)
        if not res_id:
            return {"status": "No Resource"}
            
        records = self._query_datastore(res_id, limit=5)
        return {
            "source": pkg["title"],
            "latest_data": records,
            "trend": "Analyzing..."
        }

    def _get_construction_input_index(self) -> Dict:
        """
        Fetch 'Construction Input Price Index' (מדד מחירי תשומות בבנייה).
        """
        pkg = self._search_package("מדד מחירי תשומות בבנייה")
        if not pkg:
            return {"status": "Not Found"}
            
        res_id = self._get_resource_id(pkg)
        if not res_id:
            return {"status": "No Resource"}
            
        records = self._query_datastore(res_id, limit=5)
        return {
            "source": pkg["title"],
            "latest_data": records,
            "trend": "Analyzing..."
        }
