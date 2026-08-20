import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import requests
from config.settings import settings

logger = logging.getLogger(__name__)


class BrightDataClient:
    """
    Client for managing and running Bright Data scrapers via CLI and REST API.
    """

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        self.api_key = api_key or settings.BRIGHTDATA_API_KEY
        self.api_url = (api_url or settings.BRIGHTDATA_API_URL).rstrip("/")

    def _get_cli_cmd(self) -> List[str]:
        """Return base command for bdata (using npx or binary)."""
        return ["npx", "bdata"]

    def create_scraper(
        self,
        url: str,
        description: str,
        name: Optional[str] = None,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """
        Build a scraper from a natural-language description using AI.
        Wraps `bdata scraper create`.
        """
        cmd = self._get_cli_cmd() + ["scraper", "create", url, description, "--json", "--timeout", str(timeout)]
        if name:
            cmd.extend(["--name", name])

        logger.info(f"Creating scraper for {url} with prompt: {description}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create scraper: {result.stderr or result.stdout}")

        # Parse JSON output
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            # Look for JSON block in stdout
            lines = result.stdout.strip().split("\n")
            for i in range(len(lines)):
                chunk = "\n".join(lines[i:])
                try:
                    return json.loads(chunk)
                except Exception:
                    continue
            raise RuntimeError(f"Could not parse create output: {result.stdout}")

    def run_scraper(
        self,
        collector_id: str,
        urls: Union[str, List[str]],
        sync: bool = False,
        timeout: int = 600,
    ) -> List[Dict[str, Any]]:
        """
        Run a scraper on one or more URLs and return the extracted records as a list of dicts.
        Wraps `bdata scraper run`.
        """
        if isinstance(urls, str):
            url_list = [urls]
        else:
            url_list = list(urls)

        if not url_list:
            return []

        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
            out_path = tf.name

        try:
            cmd = self._get_cli_cmd() + [
                "scraper", "run", collector_id,
                "--json",
                "--timeout", str(timeout),
                "-o", out_path
            ]

            if len(url_list) == 1:
                cmd.append(url_list[0])
                if sync:
                    cmd.append("--sync")
            else:
                # Multiple URLs passed as comma separated or input file
                input_file_path = None
                with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as inf:
                    json.dump([{"url": u} for u in url_list], inf)
                    input_file_path = inf.name
                
                cmd.extend(["--input-file", input_file_path])

            logger.info(f"Executing bdata scraper run on {len(url_list)} URL(s) using {collector_id}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 60)

            if result.returncode != 0 and not Path(out_path).exists():
                raise RuntimeError(f"Scraper execution failed (code {result.returncode}): {result.stderr or result.stdout}")

            # Read results from out_path
            if Path(out_path).exists() and os.path.getsize(out_path) > 0:
                with open(out_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        parsed = json.loads(content)
                        if isinstance(parsed, list):
                            return parsed
                        if isinstance(parsed, dict):
                            return [parsed]

            # Fallback parse from stdout if file empty
            stdout_str = result.stdout.strip()
            if stdout_str:
                # Find start of JSON array or object
                start_idx = stdout_str.find("[")
                if start_idx != -1:
                    json_str = stdout_str[start_idx:]
                    parsed = json.loads(json_str)
                    return parsed if isinstance(parsed, list) else [parsed]

            return []

        finally:
            if Path(out_path).exists():
                try:
                    os.remove(out_path)
                except Exception:
                    pass

    def run_via_api_dca_trigger(
        self,
        collector_id: str,
        urls: List[str],
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Trigger collection via REST POST /dca/trigger.
        Endpoint: https://api.brightdata.com/dca/trigger?collector=c_xxx&queue_next=1
        """
        if not self.api_key:
            raise ValueError("BRIGHTDATA_API_KEY is required for REST API calls.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        params = {
            "collector": collector_id,
            "queue_next": "1",
        }
        if webhook_url:
            params["endpoint"] = webhook_url

        payload = [{"url": u} for u in urls]
        resp = requests.post(
            f"{self.api_url}/dca/trigger",
            headers=headers,
            params=params,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def heal_scraper(
        self,
        collector_id: str,
        prompt: str,
        auto_approve: bool = True,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """
        Fix an existing scraper in place via AI self-healing.
        Wraps `bdata scraper heal`.
        """
        cmd = self._get_cli_cmd() + [
            "scraper", "heal", collector_id, prompt,
            "--json",
            "--timeout", str(timeout),
        ]
        if auto_approve:
            cmd.extend(["--auto-approve", "--auto-save"])

        logger.info(f"Triggering scraper heal for {collector_id}: {prompt}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 60)

        if result.returncode != 0:
            raise RuntimeError(f"Heal failed: {result.stderr or result.stdout}")

        try:
            return json.loads(result.stdout.strip())
        except Exception:
            return {"status": "triggered", "raw_output": result.stdout}


bdata_client = BrightDataClient()
