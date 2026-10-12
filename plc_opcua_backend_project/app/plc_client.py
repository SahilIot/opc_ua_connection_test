import os
from asyncua import Client
from app.config import env_path, required_env

async def create_plc_client() -> Client:
    endpoint = required_env("OPCUA_ENDPOINT")
    if not endpoint.startswith("opc.tcp://"):
        raise RuntimeError("OPCUA_ENDPOINT must begin with opc.tcp://")

    client_cert = env_path("OPCUA_CLIENT_CERT")
    client_key = env_path("OPCUA_CLIENT_KEY")
    server_cert = env_path("OPCUA_SERVER_CERT")

    username = os.getenv("OPCUA_USERNAME", "").strip()
    password = os.getenv("OPCUA_PASSWORD", "")
    if bool(username) != bool(password):
        raise RuntimeError(
            "Set both OPCUA_USERNAME and OPCUA_PASSWORD, or leave both blank."
        )

    client = Client(url=endpoint, timeout=10)
    security_string = (
        f"Basic256Sha256,SignAndEncrypt,{client_cert},{client_key},{server_cert}"
    )
    await client.set_security_string(security_string)

    if username:
        client.set_user(username)
        client.set_password(password)
    return client

async def test_plc_connection() -> dict:
    client = await create_plc_client()
    try:
        async with client:
            node = client.get_node("i=2258")
            data_value = await node.read_data_value()
            status = data_value.StatusCode
            if status is not None and not status.is_good():
                raise RuntimeError(f"OPC UA server-time read returned bad status: {status}")
            return {
                "connected": True,
                "endpoint": os.getenv("OPCUA_ENDPOINT", "").strip(),
                "test": "read_only",
                "node_id": "i=2258",
                "server_time": str(data_value.Value.Value),
                "status": str(status),
                "message": "OPC UA server-time read succeeded. This does not yet verify machine NodeIds.",
            }
    except Exception as exc:
        raise RuntimeError(
            f"OPC UA connection/read test failed: {type(exc).__name__}: {exc}"
        ) from exc