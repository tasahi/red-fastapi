""" MCP (Model Context Protocol) Data Types.\n
Follows official Model Context Protocol 2024-11-05 specifications
for Tools, Resources, Prompts, and Execution Results.
Option C compatible.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class Implementation(BaseModel):
    name: str
    version: str


class ClientCapabilities(BaseModel):
    experimental: Optional[Dict[str, Any]] = None
    roots: Optional[Dict[str, Any]] = None
    sampling: Optional[Dict[str, Any]] = None


class ServerCapabilities(BaseModel):
    experimental: Optional[Dict[str, Any]] = None
    logging: Optional[Dict[str, Any]] = None
    prompts: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None
    tools: Optional[Dict[str, Any]] = None


class InitializeParams(BaseModel):
    protocolVersion: str
    capabilities: ClientCapabilities = Field(default_factory=ClientCapabilities)
    clientInfo: Implementation


class InitializeResult(BaseModel):
    protocolVersion: str = "2024-11-05"
    capabilities: ServerCapabilities
    serverInfo: Implementation


class ToolInputSchema(BaseModel):
    type: Literal["object"] = "object"
    properties: Optional[Dict[str, Any]] = Field(default_factory=dict)
    required: Optional[List[str]] = Field(default_factory=list)


class Tool(BaseModel):
    name: str
    description: Optional[str] = ""
    inputSchema: ToolInputSchema = Field(default_factory=ToolInputSchema)


class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    type: Literal["image"] = "image"
    data: str
    mimeType: str


class EmbeddedResource(BaseModel):
    type: Literal["resource"] = "resource"
    resource: Dict[str, Any]


ContentItem = Union[TextContent, ImageContent, EmbeddedResource]


class CallToolResult(BaseModel):
    content: List[ContentItem] = Field(default_factory=list)
    isError: Optional[bool] = False


class Resource(BaseModel):
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None


class ResourceContent(BaseModel):
    uri: str
    mimeType: Optional[str] = None
    text: Optional[str] = None
    blob: Optional[str] = None


class ReadResourceResult(BaseModel):
    contents: List[ResourceContent] = Field(default_factory=list)


class Prompt(BaseModel):
    name: str
    description: Optional[str] = None
    arguments: Optional[List[Dict[str, Any]]] = None
