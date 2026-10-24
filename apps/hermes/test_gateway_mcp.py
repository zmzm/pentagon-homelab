"""MCP discovery registration and authenticated gateway transport, using local fixtures."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel, Field


spec = importlib.util.spec_from_file_location('gateway_mcp', Path(__file__).with_name('gateway_mcp.py'))
bridge = importlib.util.module_from_spec(spec)
with patch.dict(os.environ, {'GATEWAY_TOKEN': 'fixture-gateway-token',
                             'GATEWAY_URL': 'http://gateway.fixture:8080'}):
    spec.loader.exec_module(bridge)


class ServiceDiscovery(unittest.TestCase):
    def test_registered_mcp_discovery_needs_audit_context_but_no_target_or_approval(self):
        tools = asyncio.run(bridge.mcp.list_tools())
        tool = next(tool for tool in tools if tool.name == 'homelab_list_services')
        # SDK Python fields vary; aliases preserve the MCP wire-format names.
        schema = tool.model_dump(by_alias=True)['inputSchema']
        self.assertEqual(set(schema['properties']), {'session_id', 'user_request'})
        self.assertEqual(set(schema['required']), {'session_id', 'user_request'})
        self.assertIn('configured tool coverage', tool.description)
        self.assertIn('informational', tool.description)

    def test_schema_serialization_supports_both_python_field_names(self):
        # Pydantic fixtures model field layouts, not additional installed SDKs.
        class CamelCaseTool(BaseModel):
            inputSchema: dict

        class SnakeCaseTool(BaseModel):
            input_schema: dict = Field(alias='inputSchema')

        schema = {'type': 'object',
                  'properties': {'session_id': {'type': 'string'},
                                 'user_request': {'type': 'string'}},
                  'required': ['session_id', 'user_request']}
        for model in (CamelCaseTool, SnakeCaseTool):
            with self.subTest(python_layout=model.__name__):
                tool = model(inputSchema=schema)
                self.assertEqual(tool.model_dump(by_alias=True)['inputSchema'], schema)

    def test_discovery_forwards_only_authenticated_get_and_audit_headers(self):
        payload = {'success': True, 'data': {'coverage': 'configured_tool_coverage',
                   'services': [{'service': 'custom_app', 'restart': 'DENY'}]}}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with patch.object(bridge.urllib.request, 'urlopen', return_value=response) as upstream:
            result = bridge.homelab_list_services('session /1', 'What coverage is configured?')
        self.assertEqual(result, payload)
        request = upstream.call_args.args[0]
        self.assertEqual(request.full_url, 'http://gateway.fixture:8080/homelab/services')
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-gateway-token')
        self.assertEqual(request.get_header('X-session-id'), 'session%20%2F1')
        self.assertEqual(request.get_header('X-user-request'), 'What%20coverage%20is%20configured%3F')
        self.assertIsNone(request.get_header('X-approval-id'))

    def test_discovery_preserves_authentication_failure(self):
        error = bridge.urllib.error.HTTPError('http://gateway.fixture', 401, 'Unauthorized', {}, None)
        with patch.object(error, 'read', return_value=b'{"success":false,"error":"UNAUTHORIZED"}'), \
                patch.object(bridge.urllib.request, 'urlopen', side_effect=error):
            self.assertEqual(bridge.homelab_list_services('session', 'Discover coverage'),
                             {'success': False, 'error': 'UNAUTHORIZED'})


if __name__ == '__main__':
    unittest.main()
