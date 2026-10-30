import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_public_config_endpoint(client: AsyncClient):
    response = await client.get("/api/v1/config/public")
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "DocIntel AI"
    assert data["registration_mode"] in ("open", "disabled")
    assert ".pdf" in data["allowed_extensions"]
    assert isinstance(data["upload_max_file_bytes"], int)
    assert isinstance(data["upload_max_files"], int)
    assert "direct_upload_available" in data
    currencies = {c["code"]: c["minor_units"] for c in data["currencies"]}
    assert currencies["USD"] == 2 and currencies["JPY"] == 0 and currencies["KWD"] == 3
